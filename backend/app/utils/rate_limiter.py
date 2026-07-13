"""Per-user, per-action rate limiting backed by the rate_limit_log table."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

RATE_LIMITS = {
    "tailor_generate":    {"count": 20, "hours": 24},
    "domain_generate":    {"count": 5,  "hours": 24},
    "career_analyse":     {"count": 3,  "hours": 24},
    "jd_parse":           {"count": 50, "hours": 24},
    "gmail_poll_manual":  {"count": 3,  "hours": 1},
    "scanner_run_manual": {"count": 2,  "hours": 1},
    "feed_run_manual":    {"count": 10, "hours": 1},   # per-feed "Scan this feed" — real $ per run
}


async def enforce_rate_limit(user_id: uuid.UUID, action: str, session: AsyncSession) -> dict:
    """Raise HTTP 429 if the user has hit the limit for `action` in the rolling window;
    otherwise record one use and return {allowed, remaining, limit, window_hours}."""
    limit = RATE_LIMITS.get(action)
    if not limit:
        return {"allowed": True, "remaining": 999}

    from app.models.governance import RateLimitLog

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=limit["hours"])
    current = (await session.execute(
        select(func.coalesce(func.sum(RateLimitLog.count), 0)).where(
            RateLimitLog.user_id == user_id,
            RateLimitLog.action == action,
            RateLimitLog.window_start >= window_start,
        )
    )).scalar() or 0

    if current >= limit["count"]:
        try:
            from app.utils.audit_logger import audit_log
            await audit_log(session, "rate_limit_exceeded", user_id=user_id,
                            details={"action": action, "limit": limit["count"]}, commit=True)
        except Exception:  # noqa: BLE001 — auditing must never block the 429
            pass
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limit_exceeded",
                "message": f"Limit of {limit['count']} reached. Resets within {limit['hours']} hour(s).",
                "limit": limit["count"],
                "window_hours": limit["hours"],
            },
        )

    session.add(RateLimitLog(
        user_id=user_id, action=action, count=1,
        window_start=now, window_end=now + timedelta(hours=limit["hours"]),
    ))
    await session.flush()
    return {
        "allowed": True,
        "remaining": limit["count"] - current - 1,
        "limit": limit["count"],
        "window_hours": limit["hours"],
    }


async def rate_limit_status(user_id: uuid.UUID, session: AsyncSession) -> dict:
    """Read-only: remaining calls per action (for the Privacy tab). Records nothing."""
    from app.models.governance import RateLimitLog
    now = datetime.now(timezone.utc)
    out = {}
    for action, limit in RATE_LIMITS.items():
        window_start = now - timedelta(hours=limit["hours"])
        used = (await session.execute(
            select(func.coalesce(func.sum(RateLimitLog.count), 0)).where(
                RateLimitLog.user_id == user_id,
                RateLimitLog.action == action,
                RateLimitLog.window_start >= window_start,
            )
        )).scalar() or 0
        out[action] = {"limit": limit["count"], "used": int(used),
                       "remaining": max(0, limit["count"] - int(used)), "window_hours": limit["hours"]}
    return out
