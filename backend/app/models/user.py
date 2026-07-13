import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, Boolean, Text, Integer, ForeignKey, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped, relationship
from fastapi_users.db import SQLAlchemyBaseUserTableUUID

from app.database import Base
from app.models.base import TimestampMixin


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class UserPlan(str, Enum):
    default = "default"   # own API keys
    wallet = "wallet"     # platform keys, pay per action


class CLTone(str, Enum):
    formal = "formal"
    professional = "professional"
    conversational = "conversational"
    concise = "concise"


class CLTemplate(str, Enum):
    random = "random"
    hook_first = "hook_first"
    story_led = "story_led"
    problem_solver = "problem_solver"
    concise = "concise"


class User(SQLAlchemyBaseUserTableUUID, Base, TimestampMixin):
    """
    Core user. fastapi-users provides:
      id, email, hashed_password, is_active, is_superuser, is_verified
    We extend with role, plan, name, google_id.
    """
    __tablename__ = "users"

    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Profile fields (set from Settings → Profile)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    current_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    salary_expectation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole"),
        default=UserRole.user,
        nullable=False,
    )
    plan: Mapped[UserPlan] = mapped_column(
        SAEnum(UserPlan, name="userplan"),
        default=UserPlan.default,
        nullable=False,
    )
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )

    # ── Stripe subscription (JobHunt Pro) ──
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # inactive / active / expired / cancelled / past_due
    subscription_status: Mapped[str] = mapped_column(String(20), default="inactive", nullable=False)
    # none / pro
    subscription_plan: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    subscription_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # How the current entitlement was obtained: 'invite' | 'stripe' | 'razorpay' | None.
    # Reuses subscription_status/subscription_end above — this only records the SOURCE, so
    # the UI can show "Request extension" (invite users) vs "Manage subscription" (paid).
    entitlement_source: Mapped[Optional[str]] = mapped_column(String(20), default=None, nullable=True)

    # ── Razorpay subscription (parallel to Stripe during migration; TEST mode) ──
    razorpay_customer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    razorpay_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # Which provider granted the current PAID entitlement: 'stripe' | 'razorpay' | None.
    payment_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # GDPR / terms consent (null = not yet consented → one-time banner on login)
    gdpr_consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Right-to-erasure: 30-day grace window before purge
    data_deletion_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    data_deletion_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    credentials: Mapped[Optional["UserCredentials"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped[Optional["UserPreferences"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    wallet: Mapped[Optional["Wallet"]] = relationship(  # noqa: F821
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserCredentials(Base, TimestampMixin):
    """
    Encrypted API keys and Gmail credentials per user.
    All sensitive fields stored encrypted with Fernet.
    """
    __tablename__ = "user_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )

    # Gmail (job search account)
    gmail_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gmail_app_password_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # encrypted

    # Notification email (personal)
    notification_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # API keys (Default plan) - encrypted
    anthropic_api_key_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    apify_token_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Key-rotation timestamps (for the 90-day rotation reminder)
    anthropic_key_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    apify_token_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="credentials")


class UserPreferences(Base, TimestampMixin):
    """
    User-configurable settings — scoring, scheduling, cover letter, etc.
    """
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )

    # Target roles
    target_roles: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        default=None,   # Phase 2: no product default — pre-filter is positive-permissive
                        # until the user sets roles (onboarding). Existing rows unchanged.
    )

    # Scoring
    s1_min_threshold: Mapped[int] = mapped_column(Integer, default=65)
    s3_block_threshold: Mapped[int] = mapped_column(Integer, default=85)
    s3_review_threshold: Mapped[int] = mapped_column(Integer, default=90)

    # Ghosting
    ghost_after_days: Mapped[int] = mapped_column(Integer, default=28)

    # Follow-up
    auto_follow_up: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    follow_up_days: Mapped[int] = mapped_column(Integer, default=7)

    # Auto mode
    auto_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_include_cl: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_min_s1: Mapped[int] = mapped_column(Integer, default=80)

    # Cover letter
    cl_tone: Mapped[CLTone] = mapped_column(
        SAEnum(CLTone, name="cltone"), default=CLTone.professional
    )
    cl_template: Mapped[CLTemplate] = mapped_column(
        SAEnum(CLTemplate, name="cltemplate"), default=CLTemplate.random
    )
    cl_last_template_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Language
    language_primary: Mapped[str] = mapped_column(String(10), default="en")
    language_secondary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Gmail poll
    gmail_poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)

    # V3: Gmail job-alert parser
    parse_job_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    job_alert_max_links: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    job_alert_title_filter: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # V3: auto-detect external applications from Gmail "application sent" confirmations
    auto_detect_applications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # V3: "Email to JobHunt" — save a job URL by emailing it (subject "jobhunt"/"jh:")
    enable_email_to_jobhunt: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # V3 ATS + Pursuit dual scoring — display preferences
    default_score_view: Mapped[str] = mapped_column(String(20), default="pursuit", nullable=False)  # ats / pursuit / combined
    score_pill_style: Mapped[str] = mapped_column(String(20), default="dual_ring", nullable=False)  # dual_ring / single / number_only
    # Auto-compute ATS + Pursuit on each scanned/saved job (off by default — adds ~₹0.15/job)
    auto_dual_score_on_scan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # V3 Community Insights — opt-in anonymised sharing
    community_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── V3 Hybrid-RAG scoring config (per-user, preset-driven) ──
    scoring_preset: Mapped[str] = mapped_column(String(20), default="balanced", nullable=False)  # maximum_quality/balanced/maximum_savings
    # Stage 1 — keyword pre-filter (free)
    keyword_match_threshold: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Stage 2 — essence scoring (cheap)
    s1_essence_model: Mapped[str] = mapped_column(String(50), default="claude-haiku-4-5", nullable=False)
    s1_essence_reject_below: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Stage 3 — full CV scoring (quality)
    s1_full_model: Mapped[str] = mapped_column(String(50), default="claude-sonnet-4-6", nullable=False)
    s1_borderline_low: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    s1_borderline_high: Mapped[int] = mapped_column(Integer, default=74, nullable=False)
    # Domain CV scoring
    domain_score_model: Mapped[str] = mapped_column(String(50), default="claude-haiku-4-5", nullable=False)
    domain_score_min_s1: Mapped[int] = mapped_column(Integer, default=55, nullable=False)
    # Career insights
    career_model: Mapped[str] = mapped_column(String(50), default="claude-sonnet-4-6", nullable=False)
    # Batch size
    scoring_batch_size: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    # When to score scanned jobs: immediate / overnight (nightly batch) / manual ("Score now")
    scoring_timing: Mapped[str] = mapped_column(String(20), default="immediate", nullable=False)
    night_batch_time: Mapped[str] = mapped_column(String(10), default="02:00", nullable=False)  # IST

    # Relationships
    user: Mapped["User"] = relationship(back_populates="preferences")
