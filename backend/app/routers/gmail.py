"""
Gmail router — poll, send, reply, status.
"""
import uuid
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.config import settings
from app.models.user import User, UserCredentials
from app.models.job import Job, EmailThread, JobStatus, EmailDirection, EmailClassification
from app.models.cv import TailoredCV
from app.auth.dependencies import current_active_user
from app.utils.subscription import require_active_subscription
from app.utils.encryption import decrypt_if_present
from app.mcp.gmail_mcp import (
    poll_inbox, test_imap_connection,
    send_application_email, send_reply_email,
)
from app.agents.gmail_agents import (
    classify_emails_batch, match_email_to_job,
)
from app.utils.email import send_notification_email

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SendApplicationRequest(BaseModel):
    job_id: uuid.UUID
    tailored_cv_id: uuid.UUID
    include_cover_letter: bool = True
    custom_subject: Optional[str] = None
    recruiter_email: Optional[str] = None  # override if not in job record


class SendReplyRequest(BaseModel):
    job_id: uuid.UUID
    email_thread_id: uuid.UUID
    body: str


class PollResult(BaseModel):
    emails_checked: int
    new_emails: int
    jobs_updated: int
    hitl_flagged: int
    alerts_processed: int = 0      # V3: job-alert digest emails handled
    jobs_from_alerts: int = 0      # V3: jobs saved from those alerts
    errors: list[str] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_gmail_creds(user: User, session: AsyncSession) -> tuple[str, str]:
    """Get Gmail address and decrypted app password. Raises if not configured."""
    result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()
    if not creds or not creds.gmail_address or not creds.gmail_app_password_enc:
        raise HTTPException(
            status_code=400,
            detail="Gmail not configured. Add your Gmail address and app password in Settings → Plan & Keys.",
        )
    return creds.gmail_address, decrypt_if_present(creds.gmail_app_password_enc)


async def _get_anthropic_key(user: User, session: AsyncSession) -> Optional[str]:
    from app.models.user import UserPlan
    if user.plan == UserPlan.default:
        result = await session.execute(
            select(UserCredentials).where(UserCredentials.user_id == user.id)
        )
        creds = result.scalar_one_or_none()
        if creds and creds.anthropic_api_key_enc:
            return decrypt_if_present(creds.anthropic_api_key_enc)
    return settings.platform_anthropic_api_key or settings.anthropic_api_key


def _is_test_mode() -> bool:
    return settings.env != "production"


# ══════════════════════════════════════════════════════════════
# STATUS + CONNECTION TEST
# ══════════════════════════════════════════════════════════════

@router.get("/status")
async def gmail_status(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Gmail connection status."""
    result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()
    return {
        "configured": bool(creds and creds.gmail_address and creds.gmail_app_password_enc),
        "gmail_address": creds.gmail_address if creds else None,
        "test_mode": _is_test_mode(),
        "test_email": settings.notification_email,
    }


@router.post("/test-connection")
async def test_gmail_connection(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Test IMAP connection with stored credentials."""
    gmail_address, app_password = await _get_gmail_creds(user, session)
    result = await test_imap_connection(gmail_address, app_password)
    return result


# ══════════════════════════════════════════════════════════════
# POLL INBOX
# ══════════════════════════════════════════════════════════════

async def _handle_job_alert(e, user, session, anthropic_key, model, prefs, poll_run_id=None) -> int:
    """Create the alert EmailThread (job_id=None, is_job_alert=True) and run the
    V3 parser on it. Returns the number of jobs saved from this alert."""
    from app.agents.gmail_alert_agent import process_job_alert_email
    thread = EmailThread(
        user_id=user.id,
        job_id=None,
        gmail_message_id=e.message_id,
        direction=EmailDirection.received,
        classification=EmailClassification.job_alert,
        is_job_alert=True,
        subject=e.subject[:500] if e.subject else None,
        from_email=e.from_email,
        to_email=e.to_email,
        body_preview=e.body_preview(500),
        received_at=e.received_at,
    )
    session.add(thread)
    await session.flush()  # assign thread.id so jobs can FK source_email_id
    res = await process_job_alert_email(
        thread, e.body_html, user, session, anthropic_key, model, prefs, poll_run_id=poll_run_id)
    return res.get("saved", 0)


async def _process_inbox_emails(
    user,
    gmail_address: str,
    app_password: str,
    since_dt,
    session,
    anthropic_key,
    model: Optional[str] = None,
    poll_run_id=None,
) -> dict:
    """Shared inbox processing for the manual /poll endpoint AND the hourly
    Celery task (gmail_tasks.poll_gmail_all_users). Polls, dedupes, peels off
    job-alert digests (V3 — rule-based, no Claude), classifies the rest with
    Claude, matches to jobs, updates statuses + HITL. Commits before returning."""
    from app.models.user import UserPreferences
    from app.agents.gmail_alert_agent import is_job_alert_email, is_excluded_subject

    errors = []
    empty = {"emails_checked": 0, "new_emails": 0, "jobs_updated": 0, "hitl_flagged": 0,
             "alerts_processed": 0, "jobs_from_alerts": 0, "errors": errors}

    try:
        raw_emails = await poll_inbox(gmail_address, app_password, since_dt=since_dt)
    except Exception as e:
        errors.append(f"IMAP poll failed: {e}")
        return empty

    if not raw_emails:
        return empty

    # Skip already-processed message IDs
    existing_ids_result = await session.execute(
        select(EmailThread.gmail_message_id).where(
            EmailThread.user_id == user.id,
            EmailThread.gmail_message_id.isnot(None),
        )
    )
    existing_ids = {row[0] for row in existing_ids_result}
    new_emails = [e for e in raw_emails if e.message_id and e.message_id not in existing_ids]
    if not new_emails:
        return {**empty, "emails_checked": len(raw_emails)}

    # Preferences (V3 alert settings + model). getattr defaults keep this working
    # before step 5 adds the prefs columns.
    prefs = (await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )).scalar_one_or_none()
    parse_alerts = getattr(prefs, "parse_job_alerts", True)
    if model is None:
        model = getattr(prefs, "preferred_model", None)

    alerts_processed = 0
    jobs_from_alerts = 0

    # ── V3: peel off job-alert digests first (rule-based, no Claude call) ────
    alert_ids = set()
    if parse_alerts:
        for e in new_emails:
            try:
                if await is_job_alert_email(e.subject, e.from_email, e.body_html):
                    alert_ids.add(e.message_id)
            except Exception as ex:
                errors.append(f"alert detect {e.message_id}: {ex}")
        for e in new_emails:
            if e.message_id in alert_ids:
                try:
                    jobs_from_alerts += await _handle_job_alert(
                        e, user, session, anthropic_key, model, prefs, poll_run_id)
                    alerts_processed += 1
                except Exception as ex:
                    errors.append(f"alert process {e.message_id}: {ex}")

    other_emails = [e for e in new_emails if e.message_id not in alert_ids]

    jobs_updated = 0
    hitl_flagged = 0

    if other_emails:
        # Load active jobs for matching
        jobs_result = await session.execute(
            select(Job).where(
                Job.user_id == user.id,
                Job.status.in_([
                    JobStatus.applied, JobStatus.screening,
                    JobStatus.interview_r1, JobStatus.interview_r2,
                ])
            )
        )
        active_jobs = jobs_result.scalars().all()
        jobs_dicts = [
            {"id": str(j.id), "company": j.company, "role": j.role, "recruiter_email": j.recruiter_email}
            for j in active_jobs
        ]

        email_batch = [
            {"id": e.message_id, "from_email": e.from_email, "subject": e.subject,
             "body_preview": e.body_preview(300)}
            for e in other_emails
        ]
        try:
            classifications = await classify_emails_batch(email_batch, anthropic_key)
            class_map = {c["id"]: c for c in classifications}
        except Exception as e:
            errors.append(f"Classification failed: {e}")
            class_map = {}

        for email_msg in other_emails:
            try:
                classification_data = class_map.get(email_msg.message_id, {})
                classification = classification_data.get("classification", "unclear")
                needs_hitl = classification_data.get("needs_hitl", False)
                summary = classification_data.get("summary", "")

                # Claude flagged a job alert the rule-based pass missed
                if classification == "job_alert":
                    if parse_alerts and not is_excluded_subject(email_msg.subject):
                        try:
                            jobs_from_alerts += await _handle_job_alert(
                                email_msg, user, session, anthropic_key, model, prefs, poll_run_id)
                            alerts_processed += 1
                        except Exception as ex:
                            errors.append(f"alert process {email_msg.message_id}: {ex}")
                    continue

                # Match to job
                job_id_str = await match_email_to_job(
                    email_msg.from_email,
                    email_msg.subject,
                    email_msg.body_preview(500),
                    jobs_dicts,
                )

                # Save email thread record
                thread = EmailThread(
                    user_id=user.id,
                    job_id=uuid.UUID(job_id_str) if job_id_str else None,
                    gmail_message_id=email_msg.message_id,
                    direction=EmailDirection.received,
                    classification=EmailClassification(classification) if classification in [e.value for e in EmailClassification] else EmailClassification.unclear,
                    subject=email_msg.subject[:500] if email_msg.subject else None,
                    from_email=email_msg.from_email,
                    to_email=email_msg.to_email,
                    body_preview=email_msg.body_preview(500),
                    needs_hitl=needs_hitl,
                    received_at=email_msg.received_at,
                )
                session.add(thread)

                if job_id_str:
                    job_result = await session.execute(
                        select(Job).where(Job.id == uuid.UUID(job_id_str))
                    )
                    job = job_result.scalar_one_or_none()

                    if job:
                        # Update job status based on classification
                        if classification == "interview_invite":
                            job.status = JobStatus.screening
                            jobs_updated += 1
                        elif classification == "auto_rejection":
                            job.status = JobStatus.rejected
                            jobs_updated += 1
                        elif classification == "offer":
                            job.status = JobStatus.offer_received
                            jobs_updated += 1
                        elif classification in ("genuine_recruiter", "interview_invite", "offer"):
                            job.status = JobStatus.screening
                            jobs_updated += 1

                        # Flag HITL
                        if needs_hitl:
                            job.needs_hitl = True
                            hitl_flagged += 1

                            # Send notification to personal email
                            notification_email = None
                            creds_result = await session.execute(
                                select(UserCredentials).where(UserCredentials.user_id == user.id)
                            )
                            creds = creds_result.scalar_one_or_none()
                            if creds and creds.notification_email:
                                notification_email = creds.notification_email

                            if notification_email:
                                await send_notification_email(
                                    to=notification_email,
                                    subject=f"🔴 Action needed — {job.company} replied",
                                    message=f"<strong>{email_msg.from_email}</strong> replied about your application for <strong>{job.role}</strong> at <strong>{job.company}</strong>.<br><br>Subject: {email_msg.subject}<br><br>Preview: {email_msg.body_preview(200)}",
                                )

            except Exception as e:
                errors.append(f"Error processing email {email_msg.message_id}: {e}")
                continue

    await session.commit()

    return {
        "emails_checked": len(raw_emails),
        "new_emails": len(new_emails),
        "jobs_updated": jobs_updated,
        "hitl_flagged": hitl_flagged,
        "alerts_processed": alerts_processed,
        "jobs_from_alerts": jobs_from_alerts,
        "errors": errors,
    }


@router.post("/poll", response_model=PollResult,
             dependencies=[Depends(require_active_subscription)])
async def poll_gmail(
    since_hours: int = 24,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Manual Gmail poll. Peels off job-alert digests (V3), classifies the rest,
    matches to jobs, updates statuses, flags HITL.

    since_hours: how far back to look (default 24h)
    """
    gmail_address, app_password = await _get_gmail_creds(user, session)
    anthropic_key = await _get_anthropic_key(user, session)
    since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    summary = await _process_inbox_emails(
        user=user,
        gmail_address=gmail_address,
        app_password=app_password,
        since_dt=since_dt,
        session=session,
        anthropic_key=anthropic_key,
    )
    return PollResult(**summary)


# ══════════════════════════════════════════════════════════════
# SEND APPLICATION
# ══════════════════════════════════════════════════════════════

@router.post("/send-application", dependencies=[Depends(require_active_subscription)])
async def send_application(
    body: SendApplicationRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Send application email with tailored CV and cover letter.
    Test mode → redirects to notification_email.
    Prod mode → sends to recruiter.
    """
    gmail_address, app_password = await _get_gmail_creds(user, session)

    # Load job
    job_result = await session.execute(
        select(Job).where(Job.id == body.job_id, Job.user_id == user.id)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    recruiter_email = body.recruiter_email or job.recruiter_email
    if not recruiter_email and not _is_test_mode():
        raise HTTPException(
            status_code=400,
            detail="No recruiter email found. Add it to the job record or paste it here.",
        )
    if not recruiter_email:
        recruiter_email = settings.notification_email or gmail_address

    # Load tailored CV
    tcv_result = await session.execute(
        select(TailoredCV).where(
            TailoredCV.id == body.tailored_cv_id,
            TailoredCV.user_id == user.id,
        )
    )
    tailored = tcv_result.scalar_one_or_none()
    if not tailored:
        raise HTTPException(status_code=404, detail="Tailored CV not found")

    # Build subject
    subject = body.custom_subject or f"Application — {job.role} at {job.company}"

    # Build body from email draft
    email_body = tailored.email_draft or f"""
<p>Dear Hiring Team,</p>
<p>I am writing to express my interest in the {job.role} position at {job.company}.</p>
<p>Please find my CV{' and cover letter' if body.include_cover_letter else ''} attached.</p>
<p>I look forward to hearing from you.</p>
<p>Best regards,<br>{user.name or user.email}</p>
"""
    # Convert plain text email draft to HTML
    if email_body and not email_body.strip().startswith("<"):
        email_body = email_body.replace("\n", "<br>")

    creds_result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = creds_result.scalar_one_or_none()

    result = await send_application_email(
        gmail_address=gmail_address,
        app_password=app_password,
        to_email=recruiter_email,
        subject=subject,
        body=email_body,
        cv_pdf_path=tailored.cv_pdf_path,
        cl_pdf_path=tailored.cl_pdf_path if body.include_cover_letter else None,
        test_mode=_is_test_mode(),
        test_email=creds.notification_email if creds else None,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to send: {result.get('error')}")

    # Record in email thread
    thread = EmailThread(
        user_id=user.id,
        job_id=job.id,
        gmail_message_id=result.get("message_id"),
        direction=EmailDirection.sent,
        classification=EmailClassification.sent_application,
        subject=subject,
        from_email=gmail_address,
        to_email=result["sent_to"],
        body_preview=email_body[:500],
        cv_pdf_attached=bool(tailored.cv_pdf_path),
        cl_pdf_attached=bool(tailored.cl_pdf_path) and body.include_cover_letter,
        sent_at=datetime.now(timezone.utc),
    )
    session.add(thread)

    # Update job status + recruiter email
    job.status = JobStatus.applied
    job.applied_at = datetime.now(timezone.utc)
    if recruiter_email:
        job.recruiter_email = recruiter_email

    await session.commit()

    return {
        "success": True,
        "sent_to": result["sent_to"],
        "test_mode": result["test_mode"],
        "message_id": result.get("message_id"),
        "job_status": "applied",
    }


# ══════════════════════════════════════════════════════════════
# SEND REPLY (HITL)
# ══════════════════════════════════════════════════════════════

@router.post("/reply")
async def send_hitl_reply(
    body: SendReplyRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Send a HITL reply to a recruiter email.
    Always HITL — never auto-sent.
    """
    gmail_address, app_password = await _get_gmail_creds(user, session)

    # Load job
    job_result = await session.execute(
        select(Job).where(Job.id == body.job_id, Job.user_id == user.id)
    )
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Load original email thread
    thread_result = await session.execute(
        select(EmailThread).where(
            EmailThread.id == body.email_thread_id,
            EmailThread.user_id == user.id,
        )
    )
    original = thread_result.scalar_one_or_none()

    to_email = original.from_email if original else job.recruiter_email
    subject = original.subject if original else f"Re: {job.role} at {job.company}"
    in_reply_to = original.gmail_message_id if original else None

    if not to_email:
        raise HTTPException(status_code=400, detail="No recruiter email to reply to")

    creds_result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = creds_result.scalar_one_or_none()

    result = await send_reply_email(
        gmail_address=gmail_address,
        app_password=app_password,
        to_email=to_email,
        subject=subject,
        body=body.body.replace("\n", "<br>"),
        in_reply_to=in_reply_to,
        test_mode=_is_test_mode(),
        test_email=creds.notification_email if creds else None,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to send: {result.get('error')}")

    # Save reply in thread
    reply_thread = EmailThread(
        user_id=user.id,
        job_id=job.id,
        gmail_message_id=result.get("message_id"),
        direction=EmailDirection.sent,
        classification=EmailClassification.sent_application,
        subject=subject,
        from_email=gmail_address,
        to_email=result["sent_to"],
        body_preview=body.body[:500],
        sent_at=datetime.now(timezone.utc),
    )
    session.add(reply_thread)

    # Clear HITL flag
    job.needs_hitl = False
    await session.commit()

    return {
        "success": True,
        "sent_to": result["sent_to"],
        "test_mode": result["test_mode"],
    }
