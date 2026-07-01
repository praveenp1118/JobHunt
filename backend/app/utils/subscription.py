"""
Subscription / entitlement gate — a FastAPI dependency that enforces an active
entitlement on paid (Claude-calling) endpoints. Returns the User on success so it
can drop-in replace `current_active_user`.

A user is ENTITLED when either path is live:
  - invite : redeemed an invitation key → subscription_status='active',
             subscription_end=now+grants_days, entitlement_source='invite'
  - stripe : subscribed → subscription_status='active', subscription_end refreshed
             by the Stripe webhook, entitlement_source='stripe'

Entitlement REUSES the existing `subscription_status` + `subscription_end` columns
(no duplication). The gate is expiry-aware: `status='active'` but a past
`subscription_end` counts as LAPSED → 402 (this is how an invited user's free
period ends without any background job — there's no Stripe webhook to flip it).

Admins (the platform owner) are never paywalled. Read-only / auth / billing /
dashboard endpoints are NOT gated.
"""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

from app.models.user import User, UserRole
from app.auth.dependencies import current_active_user


def is_entitled(user: User) -> bool:
    """True if the user may use paid/Claude features right now.

    Admins always. Otherwise: subscription_status must be 'active' AND, if a
    subscription_end is set, it must be in the future (lapsed invite/sub → False)."""
    if user.role == UserRole.admin:
        return True
    if user.subscription_status != "active":
        return False
    end = user.subscription_end
    if end is not None:
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end < datetime.now(timezone.utc):
            return False
    return True


async def require_active_subscription(
    user: User = Depends(current_active_user),
) -> User:
    if is_entitled(user):
        return user
    raise HTTPException(
        status_code=402,
        detail={
            "code": "entitlement_required",
            "message": "Redeem an invitation key or subscribe to use this feature.",
            "subscription_status": user.subscription_status,
            "entitlement_source": user.entitlement_source,
        },
    )
