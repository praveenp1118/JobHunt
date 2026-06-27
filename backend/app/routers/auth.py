"""
Auth router — login, register, forgot/reset password, profile, credentials, preferences.
FastAPI-Users handles the heavy lifting; we add custom endpoints on top.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi_users.authentication import JWTStrategy
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import settings
from app.models.user import User, UserCredentials, UserPreferences
from app.auth.config import fastapi_users, auth_backend, auth_backend_long, get_jwt_strategy, get_jwt_strategy_long
from app.auth.manager import get_user_manager, UserManager
from app.auth.dependencies import current_active_user, require_admin
from app.schemas.user import (
    UserRead, UserCreate, UserUpdate,
    LoginRequest, LoginResponse,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
    ProfileUpdate, CredentialsUpdate, CredentialsRead, PreferencesUpdate,
    AdminUserUpdate, InviteCodeCreate,
)
from app.utils.encryption import encrypt_if_present, decrypt_if_present

router = APIRouter()


# ── Custom Login (supports remember_me) ──────────────────────────────────────
@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_db),
):
    """
    Login with email + password.
    remember_me=True issues a 30-day token instead of 7-day.
    Locks out after 5 failed attempts per email for 15 minutes.
    """
    from app.utils.login_security import is_locked_out, record_failure, clear_attempts
    from app.utils.audit_logger import audit_log

    if await is_locked_out(credentials.email):
        await audit_log(session, "login_failure", request=request,
                        details={"email": credentials.email, "reason": "locked_out"}, commit=True)
        raise HTTPException(status_code=429,
                            detail="Too many failed attempts. Please try again in 15 minutes.")

    # Authenticate user
    user = await user_manager.authenticate(
        type("Creds", (), {"username": credentials.email, "password": credentials.password})()
    )
    if user is None or not user.is_active:
        await record_failure(credentials.email)
        await audit_log(session, "login_failure", user_id=(user.id if user else None), request=request,
                        details={"email": credentials.email}, commit=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )

    await clear_attempts(credentials.email)

    # Issue token with appropriate lifetime
    if credentials.remember_me:
        strategy = get_jwt_strategy_long()
        token = await strategy.write_token(user)
    else:
        strategy = get_jwt_strategy()
        token = await strategy.write_token(user)

    await audit_log(session, "login_success", user_id=user.id, request=request, commit=True)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserRead.model_validate(user),
    )


# ── Register ─────────────────────────────────────────────────────────────────
@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_db),
):
    """Register a new user."""
    try:
        user = await user_manager.create(user_create, safe=True)
        from app.utils.audit_logger import audit_log
        await audit_log(session, "register", user_id=user.id, request=request,
                        details={"email": user.email}, commit=True)
        return UserRead.model_validate(user)
    except Exception as e:
        error = str(e)
        if "already exists" in error.lower() or "REGISTER_USER_ALREADY_EXISTS" in error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Forgot password ───────────────────────────────────────────────────────────
@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Request a password reset email."""
    try:
        user = await user_manager.get_by_email(body.email)
        await user_manager.forgot_password(user, request)
    except Exception:
        pass  # Never reveal if email exists
    return {"message": "If that email is registered, a reset link has been sent."}


# ── Reset password ────────────────────────────────────────────────────────────
@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
):
    """Reset password using token from email."""
    try:
        await user_manager.reset_password(body.token, body.password, request)
        return {"message": "Password updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )


# ── Change password (logged in) ───────────────────────────────────────────────
@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Change password while logged in (requires current password)."""
    # Verify current password
    verified = user_manager.password_helper.verify_and_update(
        body.current_password, user.hashed_password
    )
    if not verified[0]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    # Update password
    hashed = user_manager.password_helper.hash(body.new_password)
    user.hashed_password = hashed
    await user_manager.user_db.session.commit()
    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Audit the logout (JWT is stateless — the client discards the token)."""
    from app.utils.audit_logger import audit_log
    await audit_log(session, "logout", user_id=user.id, request=request, commit=True)
    return {"ok": True}


# ── Current user ──────────────────────────────────────────────────────────────
@router.get("/me", response_model=UserRead)
async def get_me(user: User = Depends(current_active_user)):
    """Get current user profile."""
    return UserRead.model_validate(user)


@router.post("/consent")
async def record_consent(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Record the user's agreement to the Terms of Service + Privacy Policy (GDPR).
    Idempotent — only stamps `gdpr_consent_at` the first time."""
    from datetime import datetime, timezone
    if not user.gdpr_consent_at:
        user.gdpr_consent_at = datetime.now(timezone.utc)
        await session.commit()
    return {"gdpr_consent_at": user.gdpr_consent_at}


# ── Update profile ────────────────────────────────────────────────────────────
@router.patch("/me/profile", response_model=UserRead)
async def update_profile(
    update: ProfileUpdate,
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Update display name and profile fields."""
    from app.utils.audit_logger import audit_log
    await audit_log(session, "profile_update", user_id=user.id, request=request)
    if update.name is not None:
        user.name = update.name
    if update.linkedin_url is not None:
        user.linkedin_url = update.linkedin_url
    if update.phone is not None:
        user.phone = update.phone
    if update.current_location is not None:
        user.current_location = update.current_location
    if update.salary_expectation is not None:
        user.salary_expectation = update.salary_expectation

    # Update preferences fields. Create the preferences row if the user
    # doesn't have one yet — otherwise target_roles is silently dropped
    # (mirrors the upsert in update_preferences below).
    if update.target_roles is not None:
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id)
        )
        prefs = result.scalar_one_or_none()
        if not prefs:
            prefs = UserPreferences(user_id=user.id)
            session.add(prefs)
        prefs.target_roles = update.target_roles

    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)


# ── Get credentials (masked) ──────────────────────────────────────────────────
@router.get("/me/credentials", response_model=CredentialsRead)
async def get_credentials(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get user credentials — shows what's set, never the actual values."""
    result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()
    if not creds:
        return CredentialsRead()

    return CredentialsRead(
        gmail_address=creds.gmail_address,
        notification_email=creds.notification_email,
        has_anthropic_key=bool(creds.anthropic_api_key_enc),
        has_apify_token=bool(creds.apify_token_enc),
        has_gmail_password=bool(creds.gmail_app_password_enc),
        anthropic_key_updated_at=creds.anthropic_key_updated_at,
        apify_token_updated_at=creds.apify_token_updated_at,
    )


# ── Update credentials ────────────────────────────────────────────────────────
@router.put("/me/credentials")
async def update_credentials(
    update: CredentialsUpdate,
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Save encrypted credentials (API keys, Gmail password)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(UserCredentials).where(UserCredentials.user_id == user.id)
    )
    creds = result.scalar_one_or_none()
    if not creds:
        creds = UserCredentials(user_id=user.id)
        session.add(creds)

    updated_fields = []
    if update.gmail_address is not None:
        creds.gmail_address = update.gmail_address
    if update.gmail_app_password is not None:
        creds.gmail_app_password_enc = encrypt_if_present(update.gmail_app_password)
        updated_fields.append("gmail_password")
    if update.notification_email is not None:
        creds.notification_email = update.notification_email
    if update.anthropic_api_key is not None:
        creds.anthropic_api_key_enc = encrypt_if_present(update.anthropic_api_key)
        creds.anthropic_key_updated_at = now
        updated_fields.append("anthropic_key")
    if update.apify_token is not None:
        creds.apify_token_enc = encrypt_if_present(update.apify_token)
        creds.apify_token_updated_at = now
        updated_fields.append("apify_token")

    await session.commit()
    if updated_fields:
        from app.utils.audit_logger import audit_log
        await audit_log(session, "key_update", user_id=user.id, request=request,
                        details={"fields": updated_fields}, commit=True)
    return {"message": "Credentials saved"}


# ── Get preferences ───────────────────────────────────────────────────────────
@router.get("/me/preferences")
async def get_preferences(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Get user preferences."""
    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        return {}
    return {
        "target_roles": prefs.target_roles,
        "s1_min_threshold": prefs.s1_min_threshold,
        "s3_block_threshold": prefs.s3_block_threshold,
        "s3_review_threshold": prefs.s3_review_threshold,
        "ghost_after_days": prefs.ghost_after_days,
        "auto_follow_up": prefs.auto_follow_up,
        "follow_up_days": prefs.follow_up_days,
        "auto_mode": prefs.auto_mode,
        "auto_include_cl": prefs.auto_include_cl,
        "auto_min_s1": prefs.auto_min_s1,
        "cl_tone": prefs.cl_tone,
        "cl_template": prefs.cl_template,
        "language_primary": prefs.language_primary,
        "language_secondary": prefs.language_secondary,
        "gmail_poll_interval_minutes": prefs.gmail_poll_interval_minutes,
        # V3: Gmail job-alert parser
        "parse_job_alerts": prefs.parse_job_alerts,
        "job_alert_max_links": prefs.job_alert_max_links,
        "job_alert_title_filter": prefs.job_alert_title_filter,
        "auto_detect_applications": prefs.auto_detect_applications,
        "enable_email_to_jobhunt": prefs.enable_email_to_jobhunt,
        "default_score_view": prefs.default_score_view,
        "score_pill_style": prefs.score_pill_style,
        "community_sharing_enabled": prefs.community_sharing_enabled,
    }


# ── Update preferences ────────────────────────────────────────────────────────
@router.patch("/me/preferences")
async def update_preferences(
    update: PreferencesUpdate,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    """Update user preferences."""
    result = await session.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()
    if not prefs:
        prefs = UserPreferences(user_id=user.id)
        session.add(prefs)

    for field, value in update.model_dump(exclude_none=True).items():
        setattr(prefs, field, value)

    await session.commit()
    return {"message": "Preferences updated"}


# ── Admin: list users ─────────────────────────────────────────────────────────
@router.get("/admin/users")
async def admin_list_users(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — list all users."""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserRead.model_validate(u) for u in users]


# ── Admin: update user role/plan ──────────────────────────────────────────────
@router.patch("/admin/users/{user_id}")
async def admin_update_user(
    user_id: uuid.UUID,
    update: AdminUserUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — update user role or plan. Cannot demote yourself."""
    if user_id == admin.id and update.role is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role",
        )

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if update.role is not None:
        user.role = update.role
    if update.plan is not None:
        user.plan = update.plan
    if update.is_active is not None:
        user.is_active = update.is_active

    await session.commit()
    return UserRead.model_validate(user)


# ── Admin: reset user password ────────────────────────────────────────────────
@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: uuid.UUID,
    request: Request,
    admin: User = Depends(require_admin),
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_db),
):
    """Admin — send password reset link to a user."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await user_manager.forgot_password(user, request)
    return {"message": f"Reset link sent to {user.email}"}


# ── Invite codes ──────────────────────────────────────────────────────────────
@router.post("/admin/invite-codes")
async def create_invite_code(
    body: InviteCodeCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — generate an invite code."""
    import secrets
    from datetime import datetime, timezone, timedelta
    from app.models.admin import InviteCode

    code = f"JH-{secrets.token_hex(4).upper()}"
    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    invite = InviteCode(
        code=code,
        created_by=admin.id,
        expires_at=expires_at,
    )
    session.add(invite)
    await session.commit()
    return {"code": code, "expires_at": expires_at}


@router.get("/admin/invite-codes")
async def list_invite_codes(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin — list all invite codes."""
    from app.models.admin import InviteCode
    result = await session.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc())
    )
    codes = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "code": c.code,
            "is_used": c.is_used,
            "used_at": c.used_at,
            "expires_at": c.expires_at,
            "created_at": c.created_at,
        }
        for c in codes
    ]


# ── Admin: industry verticals (for domain CV wizard) ─────────────────────────
@router.get("/admin/industries")
async def list_industries(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    from app.models.domain import IndustryVertical
    result = await session.execute(
        select(IndustryVertical)
        .where(IndustryVertical.is_active == True)
        .order_by(IndustryVertical.label)
    )
    items = result.scalars().all()
    return [{"id": str(i.id), "code": i.code, "label": i.label} for i in items]


@router.get("/admin/functions")
async def list_functions(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    from app.models.domain import FunctionalDiscipline
    result = await session.execute(
        select(FunctionalDiscipline)
        .where(FunctionalDiscipline.is_active == True)
        .order_by(FunctionalDiscipline.label)
    )
    items = result.scalars().all()
    return [{"id": str(i.id), "code": i.code, "label": i.label} for i in items]


# ── Error logs ────────────────────────────────────────────────────────────────
@router.get("/admin/error-logs")
async def get_error_logs(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    from app.models.admin import ErrorLog
    query = select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(50)
    if user.role != "admin":
        query = query.where(ErrorLog.user_id == user.id)
    result = await session.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id),
            "action": l.action,
            "error_message": l.error_message,
            "retry_count": l.retry_count,
            "is_resolved": l.is_resolved,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.patch("/admin/error-logs/{log_id}/resolve")
async def resolve_error_log(
    log_id: uuid.UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    from app.models.admin import ErrorLog
    from datetime import datetime, timezone
    result = await session.execute(select(ErrorLog).where(ErrorLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    log.is_resolved = True
    log.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    return {"resolved": True}


# ── Admin: user management ────────────────────────────────────────────────────
@router.get("/admin/users")
async def list_users(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": str(u.id), "name": u.name, "email": u.email,
            "role": u.role, "plan": u.plan,
            "is_active": u.is_active, "created_at": u.created_at,
        }
        for u in users
    ]


@router.patch("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: uuid.UUID,
    data: dict,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.role = data.get("role", target.role)
    await session.commit()
    return {"updated": True}


@router.patch("/admin/users/{user_id}/active")
async def toggle_user_active(
    user_id: uuid.UUID,
    data: dict,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_active = data.get("is_active", target.is_active)
    await session.commit()
    return {"updated": True}
