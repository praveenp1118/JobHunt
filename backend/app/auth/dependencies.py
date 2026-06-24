from fastapi import Depends, HTTPException, status
from app.models.user import User, UserRole
from app.auth.config import fastapi_users, auth_backend


# ── Current user (required) ───────────────────────────────────────────────────
current_active_user = fastapi_users.current_user(active=True)


# ── Current user (optional — for public endpoints) ───────────────────────────
optional_user = fastapi_users.current_user(active=True, optional=True)


# ── Admin required ────────────────────────────────────────────────────────────
async def require_admin(user: User = Depends(current_active_user)) -> User:
    """
    Dependency that ensures the current user is an admin.
    Used on all admin-only endpoints.
    Frontend hiding is UX only — this is the real enforcement.
    """
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# ── Verified user (active + email verified) ───────────────────────────────────
current_verified_user = fastapi_users.current_user(active=True, verified=True)
