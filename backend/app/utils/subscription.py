"""
Subscription gate — a FastAPI dependency that enforces an active JobHunt Pro
subscription on paid (write) endpoints. Returns the User on success so it can
drop-in replace `current_active_user`.

Admins (the platform owner) are never paywalled. Read-only / auth / billing /
dashboard endpoints are NOT gated.
"""
from fastapi import Depends, HTTPException

from app.models.user import User, UserRole
from app.auth.dependencies import current_active_user


async def require_active_subscription(
    user: User = Depends(current_active_user),
) -> User:
    if user.role == UserRole.admin:
        return user
    if user.subscription_status != "active":
        raise HTTPException(
            status_code=402,
            detail={
                "code": "subscription_required",
                "message": "Active subscription required",
                "subscription_status": user.subscription_status,
            },
        )
    return user
