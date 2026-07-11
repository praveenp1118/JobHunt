"""
Access router — the invite-or-pay registration gate.

  Phase 3  invitation keys + redemption
    POST   /api/admin/invites             (admin) generate N single-use keys
    GET    /api/admin/invites             (admin) list w/ status
    POST   /api/admin/invites/{id}/revoke (admin)
    PATCH  /api/admin/invites/{id}/extend (admin) bump redemption deadline
    POST   /api/invites/redeem            redeem a key → 30 (grants_days) free days

  Phase 5  extension requests
    POST   /api/extension-requests               user asks for more free time
    GET    /api/extension-requests               user's own requests
    GET    /api/admin/extension-requests         (admin) queue + pending badge
    POST   /api/admin/extension-requests/{id}/grant  (admin) +N days
    POST   /api/admin/extension-requests/{id}/deny   (admin)
    PATCH  /api/admin/users/{id}/extend-subscription (admin) comp/grace any user

Entitlement is stored on the EXISTING users.subscription_status / subscription_end
columns (reused from Stripe) + users.entitlement_source.
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.access import InvitationKey, ExtensionRequest
from app.auth.dependencies import current_active_user, require_admin

logger = logging.getLogger("access")
router = APIRouter()

# Key alphabet — unambiguous (no 0/O, 1/I/L) so keys are easy to read/type.
_KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _gen_code() -> str:
    """JH-XXXX-XXXX from a crypto-random unambiguous alphabet."""
    part = lambda: "".join(secrets.choice(_KEY_ALPHABET) for _ in range(4))
    return f"JH-{part()}-{part()}"


def _key_status(k: InvitationKey) -> str:
    if k.is_revoked:
        return "revoked"
    if k.redeemed_by is not None:
        return "redeemed"
    exp = _aware(k.key_expires_at)
    if exp is not None and exp < _now():
        return "expired"
    return "unredeemed"


def _serialize_key(k: InvitationKey) -> dict:
    return {
        "id": str(k.id),
        "code": k.code,
        "grants_days": k.grants_days,
        "status": _key_status(k),
        "key_expires_at": k.key_expires_at,
        "redeemed_by": str(k.redeemed_by) if k.redeemed_by else None,
        "redeemed_at": k.redeemed_at,
        "is_revoked": k.is_revoked,
        "created_at": k.created_at,
    }


def _extend_user(user: User, days: int, source_if_new: str = "invite") -> datetime:
    """Grant/extend free access. Extends from the later of now / current end so an
    active user's remaining days aren't lost. Sets status active + entitlement_source."""
    base = _aware(user.subscription_end)
    if base is None or base < _now():
        base = _now()
    new_end = base + timedelta(days=days)
    user.subscription_status = "active"
    user.subscription_end = new_end
    if not user.entitlement_source:
        user.entitlement_source = source_if_new
    return new_end


# ════════════════════════════════ Phase 3 — invites ════════════════════════════

class InvitesCreate(BaseModel):
    count: int = 1
    grants_days: int = 30
    key_expires_at: Optional[datetime] = None


@router.post("/admin/invites")
async def create_invites(
    body: InvitesCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — generate N single-use invitation keys."""
    n = max(1, min(body.count, 200))
    grants_days = max(1, body.grants_days)
    created = []
    for _ in range(n):
        # Collision-check the crypto-random code (unique index also enforces it).
        code = _gen_code()
        for _attempt in range(5):
            exists = (await session.execute(
                select(InvitationKey.id).where(InvitationKey.code == code))).scalar_one_or_none()
            if not exists:
                break
            code = _gen_code()
        key = InvitationKey(
            code=code, created_by=admin.id, grants_days=grants_days,
            key_expires_at=body.key_expires_at,
        )
        session.add(key)
        created.append(key)
    await session.commit()
    for k in created:
        await session.refresh(k)
    return {"created": len(created), "keys": [_serialize_key(k) for k in created]}


@router.get("/admin/invites")
async def list_invites(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — list all invitation keys with computed status."""
    keys = (await session.execute(
        select(InvitationKey).order_by(InvitationKey.created_at.desc()))).scalars().all()
    return [_serialize_key(k) for k in keys]


@router.post("/admin/invites/{invite_id}/revoke")
async def revoke_invite(
    invite_id: uuid.UUID,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — revoke an unredeemed key (a redeemed key can't be un-granted here)."""
    key = (await session.execute(
        select(InvitationKey).where(InvitationKey.id == invite_id))).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Invite not found")
    if key.redeemed_by is not None:
        raise HTTPException(status_code=400, detail="Key already redeemed — cannot revoke")
    key.is_revoked = True
    await session.commit()
    return {"revoked": True}


class InviteExtend(BaseModel):
    key_expires_at: Optional[datetime] = None  # None → clear the deadline (never expires)


@router.patch("/admin/invites/{invite_id}/extend")
async def extend_invite(
    invite_id: uuid.UUID,
    body: InviteExtend,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — bump (or clear) an unredeemed key's redemption deadline."""
    key = (await session.execute(
        select(InvitationKey).where(InvitationKey.id == invite_id))).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Invite not found")
    if key.redeemed_by is not None:
        raise HTTPException(status_code=400, detail="Key already redeemed")
    key.key_expires_at = body.key_expires_at
    await session.commit()
    await session.refresh(key)
    return _serialize_key(key)


class RedeemBody(BaseModel):
    code: str


@router.post("/invites/redeem")
async def redeem_invite(
    body: RedeemBody,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Redeem a single-use key → grant grants_days of free access.

    Atomic + race-safe: the key row is locked (SELECT ... FOR UPDATE) so two users
    racing the same code can't both win — the second sees it redeemed and gets 400.
    Idempotent for the SAME user re-submitting a key they already redeemed."""
    code = (body.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail={"code": "invalid_key", "message": "Enter an invitation key."})

    # Lock the key row for the duration of this transaction.
    key = (await session.execute(
        select(InvitationKey).where(InvitationKey.code == code).with_for_update()
    )).scalar_one_or_none()

    if not key:
        raise HTTPException(status_code=404, detail={"code": "invalid_key", "message": "Invalid invitation key."})

    # Idempotent: same user re-redeeming a key they already used → return current state.
    if key.redeemed_by == user.id:
        return {
            "redeemed": True, "already": True,
            "subscription_status": user.subscription_status,
            "subscription_end": user.subscription_end,
            "entitlement_source": user.entitlement_source,
        }

    if key.is_revoked:
        raise HTTPException(status_code=400, detail={"code": "key_revoked", "message": "This key has been revoked."})
    if key.redeemed_by is not None:
        raise HTTPException(status_code=400, detail={"code": "key_used", "message": "This key has already been used."})
    exp = _aware(key.key_expires_at)
    if exp is not None and exp < _now():
        raise HTTPException(status_code=400, detail={"code": "key_expired", "message": "This key has expired."})

    # Mark redeemed + grant.
    now = _now()
    key.redeemed_by = user.id
    key.redeemed_at = now
    new_end = _extend_user(user, key.grants_days, source_if_new="invite")
    user.entitlement_source = "invite"
    await session.commit()

    return {
        "redeemed": True, "already": False,
        "grants_days": key.grants_days,
        "subscription_status": user.subscription_status,
        "subscription_end": new_end,
        "entitlement_source": user.entitlement_source,
    }


# ═══════════════════════════ Phase 5 — extension requests ═══════════════════════

async def _notify_admin_extension(user: User) -> None:
    """Best-effort admin email on a new extension request. NEVER raises — the in-app
    queue row is the source of truth; email is a notification on top."""
    to_addr = settings.notification_email or settings.admin_email
    sender = settings.gmail_address
    app_password = settings.gmail_app_password
    if not (to_addr and sender and app_password):
        logger.warning("extension-request email skipped — SMTP not configured (request still saved)")
        return
    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.utils import formatdate, make_msgid
        msg = MIMEText(
            f"User {user.email} (id {user.id}) requested a free-access extension.\n\n"
            f"Current status: {user.subscription_status}, ends {user.subscription_end}.\n"
            f"Review in Admin → Extension Requests.",
            "plain",
        )
        msg["From"] = f"AIJobsHunt <{sender}>"
        msg["To"] = to_addr
        msg["Subject"] = f"[AIJobsHunt] Extension request from {user.email}"
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        await aiosmtplib.send(msg, hostname="smtp.gmail.com", port=587, start_tls=True,
                              username=sender, password=app_password)
    except Exception as e:  # noqa: BLE001 — email is best-effort only
        logger.warning("extension-request admin email failed (request still saved): %s", e)


@router.post("/extension-requests")
async def create_extension_request(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Invited user asks for more free time. Saves a pending row (source of truth),
    then best-effort emails the admin. A duplicate open request is reused."""
    existing = (await session.execute(
        select(ExtensionRequest).where(
            ExtensionRequest.user_id == user.id,
            ExtensionRequest.status == "pending",
        ).order_by(ExtensionRequest.requested_at.desc())
    )).scalars().first()
    if existing:
        await _notify_admin_extension(user)
        return {"created": False, "pending": True, "id": str(existing.id)}

    req = ExtensionRequest(user_id=user.id, status="pending")
    session.add(req)
    await session.commit()
    await session.refresh(req)
    await _notify_admin_extension(user)
    return {"created": True, "pending": True, "id": str(req.id)}


@router.get("/extension-requests")
async def my_extension_requests(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """The user's own extension requests."""
    rows = (await session.execute(
        select(ExtensionRequest).where(ExtensionRequest.user_id == user.id)
        .order_by(ExtensionRequest.requested_at.desc()))).scalars().all()
    return [
        {"id": str(r.id), "status": r.status, "requested_at": r.requested_at,
         "resolved_at": r.resolved_at, "admin_note": r.admin_note}
        for r in rows
    ]


@router.get("/admin/extension-requests")
async def list_extension_requests(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — the extension queue + a pending count for the nav badge."""
    rows = (await session.execute(
        select(ExtensionRequest).order_by(ExtensionRequest.requested_at.desc()))).scalars().all()
    # Join user emails in one pass.
    user_ids = list({r.user_id for r in rows})
    emails = {}
    if user_ids:
        for u in (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            emails[u.id] = {"email": u.email, "subscription_status": u.subscription_status,
                            "subscription_end": u.subscription_end, "entitlement_source": u.entitlement_source}
    pending = sum(1 for r in rows if r.status == "pending")
    return {
        "pending_count": pending,
        "requests": [
            {"id": str(r.id), "user_id": str(r.user_id),
             "user": emails.get(r.user_id, {}),
             "status": r.status, "requested_at": r.requested_at,
             "resolved_at": r.resolved_at, "admin_note": r.admin_note}
            for r in rows
        ],
    }


class GrantBody(BaseModel):
    days: int = 30
    admin_note: Optional[str] = None


async def _resolve_request(session, request_id, admin, status_value, days=None, note=None):
    req = (await session.execute(
        select(ExtensionRequest).where(ExtensionRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    target = (await session.execute(
        select(User).where(User.id == req.user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_end = None
    if status_value == "granted":
        new_end = _extend_user(target, max(1, days or 30), source_if_new="invite")
    req.status = status_value
    req.admin_note = note
    req.resolved_at = _now()
    await session.commit()
    return req, target, new_end


@router.post("/admin/extension-requests/{request_id}/grant")
async def grant_extension_request(
    request_id: uuid.UUID,
    body: GrantBody,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — grant an extension: bumps the user's subscription_end by `days`."""
    req, target, new_end = await _resolve_request(
        session, request_id, admin, "granted", days=body.days, note=body.admin_note)
    return {"granted": True, "user_id": str(target.id),
            "subscription_end": new_end, "subscription_status": target.subscription_status}


@router.post("/admin/extension-requests/{request_id}/deny")
async def deny_extension_request(
    request_id: uuid.UUID,
    body: GrantBody,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — deny an extension request (no change to the user's entitlement)."""
    await _resolve_request(session, request_id, admin, "denied", note=body.admin_note)
    return {"denied": True}


class ExtendUserBody(BaseModel):
    days: int = 30


@router.patch("/admin/users/{user_id}/extend-subscription")
async def admin_extend_subscription(
    user_id: uuid.UUID,
    body: ExtendUserBody,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — directly extend ANY user's free access by `days` (comp / grace tool)."""
    target = (await session.execute(
        select(User).where(User.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_end = _extend_user(target, max(1, body.days), source_if_new="invite")
    await session.commit()
    return {"extended": True, "user_id": str(target.id),
            "subscription_end": new_end, "subscription_status": target.subscription_status,
            "entitlement_source": target.entitlement_source}
