"""GDPR self-service — data summary, export (ZIP), and right-to-erasure (30-day grace)."""
import io
import json
import zipfile
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.cv import MasterCV, DomainCV, TailoredCV
from app.models.job import Job, EmailThread
from app.auth.dependencies import current_active_user

router = APIRouter()
DELETION_GRACE_DAYS = 30


async def _count(session, model, user_id) -> int:
    return (await session.execute(
        select(func.count(model.id)).where(model.user_id == user_id))).scalar() or 0


@router.get("/summary")
async def privacy_summary(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    from app.models.usage import APIUsageLog
    counts = {
        "master_cvs": await _count(session, MasterCV, user.id),
        "domain_cvs": await _count(session, DomainCV, user.id),
        "jobs": await _count(session, Job, user.id),
        "tailored_cvs": await _count(session, TailoredCV, user.id),
        "usage_logs": await _count(session, APIUsageLog, user.id),
    }
    try:
        from app.models.chat import ChatMessage
        counts["chat_messages"] = (await session.execute(
            select(func.count(ChatMessage.id)))).scalar() or 0  # not user-scoped table; best-effort
    except Exception:
        counts["chat_messages"] = 0
    return {
        **counts,
        "account_created": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        "data_deletion_scheduled": user.data_deletion_scheduled_at.isoformat() if user.data_deletion_scheduled_at else None,
    }


@router.get("/rate-limits")
async def rate_limits(user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    """Read-only remaining-calls-per-action (for the Privacy tab). Records nothing."""
    from app.utils.rate_limiter import rate_limit_status
    return await rate_limit_status(user.id, session)


@router.get("/export")
async def export_data(request: Request, user: User = Depends(current_active_user),
                      session: AsyncSession = Depends(get_db)):
    """Generate an in-memory ZIP of all the user's data (JSON + markdown)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt",
                   "AIJobsHunt data export\n"
                   f"Generated: {datetime.now(timezone.utc).isoformat()}\n"
                   f"Account: {user.email}\n\n"
                   "Contents: profile.json, master_cv.md, domain_cvs/, jobs.json, "
                   "tailored_cvs/, applications.json, usage_log.json\n")

        z.writestr("profile.json", json.dumps({
            "email": user.email, "name": user.name, "linkedin_url": user.linkedin_url,
            "phone": user.phone, "current_location": user.current_location,
            "subscription_status": user.subscription_status, "subscription_plan": user.subscription_plan,
            "gdpr_consent_at": user.gdpr_consent_at.isoformat() if user.gdpr_consent_at else None,
            "account_created": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        }, indent=2, default=str))

        master = (await session.execute(
            select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True))).scalars().first()
        if master:
            z.writestr("master_cv.md", master.content_md or "")

        for dcv in (await session.execute(select(DomainCV).where(DomainCV.user_id == user.id))).scalars().all():
            z.writestr(f"domain_cvs/{dcv.id}.md", dcv.content_md or "")

        jobs = (await session.execute(select(Job).where(Job.user_id == user.id))).scalars().all()
        z.writestr("jobs.json", json.dumps([{
            "id": str(j.id), "company": j.company, "role": j.role, "market": j.market,
            "status": str(j.status), "source": str(j.source), "s1": j.s1, "s1d": j.s1d,
            "created_at": j.created_at.isoformat() if getattr(j, "created_at", None) else None,
        } for j in jobs], indent=2, default=str))

        for tcv in (await session.execute(select(TailoredCV).where(TailoredCV.user_id == user.id))).scalars().all():
            if tcv.cv_md:
                z.writestr(f"tailored_cvs/{tcv.id}.md", tcv.cv_md)

        threads = (await session.execute(select(EmailThread).where(EmailThread.user_id == user.id))).scalars().all()
        z.writestr("applications.json", json.dumps([{
            "id": str(t.id), "job_id": str(t.job_id) if t.job_id else None, "subject": t.subject,
            "direction": str(t.direction), "classification": str(t.classification),
        } for t in threads], indent=2, default=str))

        from app.models.usage import APIUsageLog
        logs = (await session.execute(select(APIUsageLog).where(APIUsageLog.user_id == user.id))).scalars().all()
        z.writestr("usage_log.json", json.dumps([{
            "provider": l.provider, "agent": l.agent_name, "category": l.category,
            "total_tokens": l.total_tokens, "cost_inr": l.estimated_cost_inr,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs], indent=2, default=str))

    from app.utils.audit_logger import audit_log
    await audit_log(session, "export_data", user_id=user.id, request=request, commit=True)

    fname = f"jobhunt_export_{user.id}.zip"
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class DeleteRequest(BaseModel):
    confirm: bool = False


@router.post("/delete-request")
async def request_deletion(body: DeleteRequest, request: Request,
                           user: User = Depends(current_active_user), session: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to request account deletion")
    now = datetime.now(timezone.utc)
    user.data_deletion_requested_at = now
    user.data_deletion_scheduled_at = now + timedelta(days=DELETION_GRACE_DAYS)

    # Best-effort: cancel the active subscription at period end so FUTURE charges stop.
    # A deletion request MUST stop the recurring mandate — but a provider hiccup must NOT
    # block the deletion, so this is wrapped and swallowed.
    try:
        import asyncio
        from app.utils.razorpay_client import is_razorpay_user, cancel_razorpay_subscription
        if is_razorpay_user(user):
            if user.razorpay_subscription_id:
                await asyncio.to_thread(
                    cancel_razorpay_subscription, user.razorpay_subscription_id, True)
                user.subscription_status = "cancelled"
        elif user.subscription_id:
            import stripe
            from app.config import settings
            stripe.api_key = settings.stripe_secret_key
            await asyncio.to_thread(stripe.Subscription.modify, user.subscription_id, cancel_at_period_end=True)
            user.subscription_status = "cancelled"
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("jobhunt").warning(f"Provider cancel during deletion failed: {e}")

    await session.commit()
    from app.utils.audit_logger import audit_log
    await audit_log(session, "delete_account_request", user_id=user.id, request=request,
                    details={"scheduled_at": user.data_deletion_scheduled_at.isoformat()}, commit=True)
    return {"scheduled": True, "scheduled_at": user.data_deletion_scheduled_at.isoformat(),
            "grace_days": DELETION_GRACE_DAYS}


@router.post("/cancel-deletion")
async def cancel_deletion(request: Request, user: User = Depends(current_active_user),
                          session: AsyncSession = Depends(get_db)):
    user.data_deletion_requested_at = None
    user.data_deletion_scheduled_at = None
    await session.commit()
    from app.utils.audit_logger import audit_log
    await audit_log(session, "delete_account_cancel", user_id=user.id, request=request, commit=True)
    return {"cancelled": True}
