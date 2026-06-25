"""Fire-and-forget audit logging. Never raises — must not break the request."""
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("jobhunt.audit")


def _client_ip(request) -> Optional[str]:
    if not request:
        return None
    # Respect a reverse proxy if present, else the socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:45]
    return getattr(getattr(request, "client", None), "host", None)


async def audit_log(
    session: AsyncSession,
    action: str,
    user_id: Optional[uuid.UUID] = None,
    request=None,
    details: Optional[dict] = None,
    commit: bool = False,
):
    """Write an AuditLog row. Best-effort: swallows all errors."""
    try:
        from app.models.governance import AuditLog
        ua = request.headers.get("user-agent") if request else None
        session.add(AuditLog(
            user_id=user_id,
            action=action,
            ip_address=_client_ip(request),
            user_agent=(ua or "")[:500] or None,
            details=details,
        ))
        if commit:
            await session.commit()
        else:
            await session.flush()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Audit log failed for action={action}: {e}")
