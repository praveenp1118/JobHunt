import uuid
from datetime import datetime
from typing import Optional
from fastapi_users import schemas
from pydantic import BaseModel, EmailStr

from app.models.user import UserRole, UserPlan, CLTone, CLTemplate


# ── FastAPI-Users base schemas ────────────────────────────────────────────────

class UserRead(schemas.BaseUser[uuid.UUID]):
    name: Optional[str] = None
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    current_location: Optional[str] = None
    salary_expectation: Optional[str] = None
    role: UserRole = UserRole.user
    plan: UserPlan = UserPlan.default
    gdpr_consent_at: Optional[datetime] = None
    # Entitlement (invite-or-pay). Reuses the Stripe subscription columns.
    subscription_status: str = "inactive"
    subscription_plan: str = "none"
    subscription_end: Optional[datetime] = None
    entitlement_source: Optional[str] = None  # 'invite' | 'stripe' | None

    class Config:
        from_attributes = True


class UserCreate(schemas.BaseUserCreate):
    name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    name: Optional[str] = None


# ── Custom auth schemas ───────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Profile update schema ─────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None
    current_location: Optional[str] = None
    target_roles: Optional[str] = None
    salary_expectation: Optional[str] = None


# ── Credentials schema ────────────────────────────────────────────────────────

class CredentialsUpdate(BaseModel):
    gmail_address: Optional[str] = None
    gmail_app_password: Optional[str] = None
    notification_email: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    apify_token: Optional[str] = None


class CredentialsRead(BaseModel):
    gmail_address: Optional[str] = None
    notification_email: Optional[str] = None
    has_anthropic_key: bool = False
    has_apify_token: bool = False
    has_gmail_password: bool = False
    anthropic_key_updated_at: Optional[datetime] = None
    apify_token_updated_at: Optional[datetime] = None


# ── Preferences schema ────────────────────────────────────────────────────────

class PreferencesUpdate(BaseModel):
    target_roles: Optional[str] = None
    s1_min_threshold: Optional[int] = None
    s3_block_threshold: Optional[int] = None
    s3_review_threshold: Optional[int] = None
    ghost_after_days: Optional[int] = None
    auto_follow_up: Optional[bool] = None
    follow_up_days: Optional[int] = None
    auto_mode: Optional[bool] = None
    auto_include_cl: Optional[bool] = None
    auto_min_s1: Optional[int] = None
    cl_tone: Optional[CLTone] = None
    cl_template: Optional[CLTemplate] = None
    language_primary: Optional[str] = None
    language_secondary: Optional[str] = None
    gmail_poll_interval_minutes: Optional[int] = None
    # V3: Gmail job-alert parser
    parse_job_alerts: Optional[bool] = None
    job_alert_max_links: Optional[int] = None
    job_alert_title_filter: Optional[bool] = None
    auto_detect_applications: Optional[bool] = None
    enable_email_to_jobhunt: Optional[bool] = None
    default_score_view: Optional[str] = None   # ats / pursuit / combined
    score_pill_style: Optional[str] = None     # dual_ring / single / number_only
    auto_dual_score_on_scan: Optional[bool] = None


# ── Admin schemas ─────────────────────────────────────────────────────────────

class AdminUserUpdate(BaseModel):
    role: Optional[UserRole] = None
    plan: Optional[UserPlan] = None
    is_active: Optional[bool] = None


class InviteCodeCreate(BaseModel):
    expires_days: Optional[int] = None  # None = never expires
