"""Auto-detect external job applications from Gmail confirmation emails.

When the Gmail poll classifies an email as `auto_confirmation` (an automated
"we received your application" / "your application was sent" message), we:
  1. extract the company (+ role) from the subject — pure regex, no Claude;
  2. match it to a job in 'new'/'bookmarked' status → flip it to 'applied';
  3. or, with no match, create a new 'applied' job (source=gmail_alert);
then link the email via an EmailThread and log it to the Activity timeline.
"""
import re
from datetime import datetime, timezone

# (regex, has_role). First match wins. Named groups: company (required), role (optional).
# Patterns target LinkedIn / Indeed / generic ATS confirmation subject lines.
_PATTERNS = [
    # "You applied to Head of Product at Adyen"
    (r"you(?:'ve| have)?\s+applied\s+(?:to|for)\s+(?P<role>.+?)\s+at\s+(?P<company>.+)", True),
    # "Application sent: Head of Product at Adyen"
    (r"application\s+sent:?\s+(?P<role>.+?)\s+at\s+(?P<company>.+)", True),
    # "Your application was sent to Tredence Inc."
    (r"your\s+application\s+(?:was\s+)?sent\s+to\s+(?P<company>.+)", False),
    # "Your application to Adyen was sent / has been received"
    (r"your\s+application\s+(?:to|for)\s+(?P<company>.+?)\s+(?:was|has|is|been)\b", False),
    # "Application submitted to Adyen" / "has been submitted to Adyen"
    (r"application\s+(?:has\s+been\s+)?submitted\s+to\s+(?P<company>.+)", False),
    # "Thanks for applying to Adyen" / "Thank you for applying to Adyen"
    (r"(?:thanks|thank you)\s+for\s+applying\s+(?:to|at)\s+(?P<company>.+)", False),
    # "Indeed Application: Head of Product - Adyen"
    (r"application:?\s+(?P<role>.+?)\s+[-–—]\s+(?P<company>.+)", True),
    # generic "applied to <role> at <company>"
    (r"applied\s+(?:to|for)\s+(?P<role>.+?)\s+at\s+(?P<company>.+)", True),
]

# Strip a trailing "... was sent/received/submitted ..." tail left on a company capture.
_TRAIL = re.compile(r"\b(was|has been|have been|is|been)\s+(sent|received|submitted|completed).*$", re.I)


def _clean(s):
    if not s:
        return None
    s = s.strip().strip(".!,–—- \t")
    s = _TRAIL.sub("", s).strip()
    s = re.sub(r"\s*[\(\[].*$", "", s).strip()        # drop trailing "(Remote)" / "[NL]" etc.
    s = re.sub(r"\s+(position|role|job)$", "", s, flags=re.I).strip()
    return s or None


def extract_company_role(subject, body=None):
    """Return (company, role) parsed from a confirmation email subject (body as fallback).
    company is None when nothing usable is found."""
    for text in (subject, (body or "").split("\n", 1)[0] if body else None):
        if not text:
            continue
        for pat, has_role in _PATTERNS:
            m = re.search(pat, text.strip(), re.I)
            if not m:
                continue
            company = _clean(m.group("company"))
            role = _clean(m.group("role")) if has_role else None
            if company and 1 < len(company) <= 80:
                return company, role
    return None, None


async def detect_external_application(email_msg, user, session, poll_run_id=None) -> dict:
    """Match/create a job for an auto_confirmation email. Adds an EmailThread + an
    EmailAlertLog (so it surfaces in Activity → Job Alerts). Returns the outcome dict
    {action: matched|created|no_company, company?, role?, job_id?}. Caller commits."""
    from sqlalchemy import select
    from app.models.job import (
        Job, EmailThread, JobStatus, JobSource, EmailDirection, EmailClassification,
    )
    from app.models.admin import EmailAlertLog
    from app.utils.community import normalize_company  # noqa: F401  (kept for parity / future use)

    company, role = extract_company_role(email_msg.subject, email_msg.body_preview(500))
    if not company:
        return {"action": "no_company"}

    received = email_msg.received_at or datetime.now(timezone.utc)

    async def _find(term):
        if not term or len(term) < 3:
            return None
        return (await session.execute(
            select(Job).where(
                Job.user_id == user.id,
                Job.status.in_([JobStatus.new, JobStatus.bookmarked]),
                Job.company.ilike(f"%{term}%"),
            ).limit(1)
        )).scalars().first()

    # ILIKE on the whole company, then fall back to its first significant word
    # ("Tredence Inc." → "Tredence") so minor suffixes don't block a match.
    match = await _find(company)
    if not match:
        first_word = company.split()[0] if company.split() else ""
        match = await _find(first_word)

    if match:
        match.status = JobStatus.applied
        match.applied_at = received
        job = match
        action = "matched"
    else:
        job = Job(
            user_id=user.id,
            company=company,
            role=role or "Unknown role",
            source=JobSource.gmail_alert,
            status=JobStatus.applied,
            applied_at=received,
            scoring_status="scored",
        )
        session.add(job)
        await session.flush()  # assign job.id for the EmailThread / log FKs
        action = "created"

    session.add(EmailThread(
        user_id=user.id,
        job_id=job.id,
        gmail_message_id=email_msg.message_id,
        direction=EmailDirection.received,
        classification=EmailClassification.auto_confirmation,
        subject=email_msg.subject[:500] if email_msg.subject else None,
        from_email=email_msg.from_email,
        to_email=email_msg.to_email,
        body_preview=email_msg.body_preview(500),
        received_at=received,
    ))

    session.add(EmailAlertLog(
        user_id=user.id,
        poll_run_id=poll_run_id,
        email_subject=email_msg.subject,
        sender=email_msg.from_email,
        received_at=received,
        jobs_saved=1,
        saved_job_ids=[str(job.id)],
        skip_reasons=[{
            "reason": "auto_application",
            "action": action,            # matched (existing job) | created (new job)
            "company": job.company,
            "role": job.role,
        }],
    ))

    return {"action": action, "company": job.company, "role": job.role, "job_id": str(job.id)}
