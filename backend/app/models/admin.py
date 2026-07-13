import uuid
from enum import Enum
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, DateTime, func, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base


class RunStatus(str, Enum):
    running = "running"
    success = "success"
    partial = "partial"
    error = "error"


class RunType(str, Enum):
    weekly_scan = "weekly_scan"
    gmail_poll = "gmail_poll"
    ghost_check = "ghost_check"
    night_batch = "night_batch"
    stub_fetch = "stub_fetch"
    followup_check = "followup_check"
    partial_enrich = "partial_enrich"   # daily Bright Data auto-enrich of high-scoring partials


class RunLog(Base):
    """
    Audit log for all scheduled and background tasks.
    User sees their own. Admin sees all.
    """
    __tablename__ = "run_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True
    )  # NULL = platform-wide run (weekly scan)

    run_type: Mapped[RunType] = mapped_column(
        SAEnum(RunType, name="runtype"), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="runstatus"), default=RunStatus.running
    )
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_added: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # per-run breakdown
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ErrorLog(Base):
    """
    Per-action error tracking with retry count.
    User sees their own errors. Admin sees all.
    """
    __tablename__ = "error_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # parse_jd, score, tailor, etc
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON extra context

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EmailAlertLog(Base):
    """
    V3: per-email record of what the Gmail job-alert parser did with one alert
    digest — powers the Activity dashboard's Job Alerts tab.
    """
    __tablename__ = "email_alert_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    poll_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("run_logs.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    email_subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    links_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    links_gated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)       # login-walled
    links_public: Mapped[int] = mapped_column(Integer, default=0, nullable=False)      # fetchable
    links_below_threshold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    links_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_saved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    saved_job_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)   # [job uuid str]
    skip_reasons: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)    # [{url, reason, s1, ...}]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InviteCode(Base):
    """
    Invite codes for controlled registration.
    """
    __tablename__ = "invite_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    used_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
