"""
Activity dashboard (read-only) — job-alert timeline + system run logs.
  GET /api/activity/alerts  — per-email job-alert processing records
  GET /api/activity/system  — scanner / gmail-poll / ghosted run logs + recent errors
"""
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.models.job import Job
from app.models.admin import RunLog, ErrorLog, EmailAlertLog, RunType
from app.auth.dependencies import current_active_user

router = APIRouter()


def _runlog_dict(r: RunLog) -> dict:
    return {
        "id": str(r.id),
        "run_type": r.run_type.value if hasattr(r.run_type, "value") else r.run_type,
        "status": r.status.value if hasattr(r.status, "value") else r.status,
        "jobs_found": r.jobs_found,
        "jobs_added": r.jobs_added,
        "details": r.details,
        "error_message": r.error_message,
        "duration_seconds": r.duration_seconds,
        "started_at": r.started_at,
        "completed_at": r.completed_at,
    }


@router.get("/alerts")
async def get_alert_activity(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Job-alert processing timeline for the current user, newest first, with
    summaries of the jobs each alert saved."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(EmailAlertLog)
        .where(EmailAlertLog.user_id == user.id, EmailAlertLog.created_at >= since)
        .order_by(func.coalesce(EmailAlertLog.received_at, EmailAlertLog.created_at).desc())
        .limit(limit)
    )).scalars().all()

    # Resolve saved_job_ids -> {company, role, s1} in one query
    job_map = {}
    wanted = []
    for r in rows:
        for jid in (r.saved_job_ids or []):
            try:
                wanted.append(uuid.UUID(str(jid)))
            except (ValueError, TypeError):
                pass
    if wanted:
        jobs = (await session.execute(select(Job).where(Job.id.in_(wanted)))).scalars().all()
        job_map = {str(j.id): {"id": str(j.id), "company": j.company, "role": j.role, "s1": j.s1} for j in jobs}

    out = []
    for r in rows:
        saved_jobs = [job_map[str(jid)] for jid in (r.saved_job_ids or []) if str(jid) in job_map]
        # Auto-detected external applications encode their outcome in skip_reasons.
        auto_app = next((x for x in (r.skip_reasons or [])
                         if isinstance(x, dict) and x.get("reason") == "auto_application"), None)
        out.append({
            "id": str(r.id),
            "email_subject": r.email_subject,
            "sender": r.sender,
            "received_at": r.received_at,
            "links_found": r.links_found,
            "links_gated": r.links_gated,
            "links_public": r.links_public,
            "links_below_threshold": r.links_below_threshold,
            "links_duplicate": r.links_duplicate,
            "jobs_saved": r.jobs_saved,
            "skip_reasons": r.skip_reasons or [],
            "saved_jobs": saved_jobs,
            "auto_application": auto_app,  # {action, company, role} when auto-detected, else null
            "created_at": r.created_at,
        })
    return out


@router.get("/system")
async def get_system_activity(
    days: int = Query(7, ge=1, le=90),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Scanner / Gmail-poll / ghosted run logs + recent errors."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async def _runs(run_type, user_scoped: bool):
        q = select(RunLog).where(RunLog.run_type == run_type, RunLog.started_at >= since)
        if user_scoped:
            q = q.where(RunLog.user_id == user.id)
        q = q.order_by(RunLog.started_at.desc()).limit(25)
        return [_runlog_dict(r) for r in (await session.execute(q)).scalars().all()]

    # weekly scan + ghosted checks are platform-wide (user_id NULL); polls are per-user
    scanner_runs = await _runs(RunType.weekly_scan, user_scoped=False)
    gmail_polls = await _runs(RunType.gmail_poll, user_scoped=True)
    ghosted_checks = await _runs(RunType.ghost_check, user_scoped=False)
    night_batches = await _runs(RunType.night_batch, user_scoped=False)

    err_q = select(ErrorLog).where(ErrorLog.created_at >= since)
    if user.role != UserRole.admin:
        err_q = err_q.where(ErrorLog.user_id == user.id)
    errors = (await session.execute(err_q.order_by(ErrorLog.created_at.desc()))).scalars().all()

    return {
        "scanner_runs": scanner_runs,
        "gmail_polls": gmail_polls,
        "ghosted_checks": ghosted_checks,
        "night_batches": night_batches,
        "error_count": len(errors),
        "recent_errors": [
            {
                "id": str(e.id),
                "action": e.action,
                "error_message": e.error_message,
                "is_resolved": e.is_resolved,
                "created_at": e.created_at,
            }
            for e in errors[:5]
        ],
    }
