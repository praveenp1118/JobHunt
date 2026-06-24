import uuid
from enum import Enum
from typing import Optional
from datetime import datetime
from sqlalchemy import (
    String, Text, Integer, Boolean, Float, ForeignKey,
    Enum as SAEnum, DateTime, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.database import Base
from app.models.base import TimestampMixin


class JobStatus(str, Enum):
    new = "new"
    bookmarked = "bookmarked"
    applied = "applied"
    screening = "screening"
    interview_r1 = "interview_r1"
    interview_r2 = "interview_r2"
    offer_received = "offer_received"
    offer_accepted = "offer_accepted"
    offer_declined = "offer_declined"
    rejected = "rejected"
    ghosted = "ghosted"
    withdrawn = "withdrawn"
    not_interested = "not_interested"


class JobSource(str, Enum):
    manual = "manual"
    url = "url"
    file = "file"
    gmail = "gmail"
    apify = "apify"
    rss = "rss"
    gmail_alert = "gmail_alert"   # V3: extracted from a job-alert digest email


class EmailDirection(str, Enum):
    sent = "sent"
    received = "received"


class EmailClassification(str, Enum):
    auto_confirmation = "auto_confirmation"
    auto_rejection = "auto_rejection"
    genuine_recruiter = "genuine_recruiter"
    interview_invite = "interview_invite"
    offer = "offer"
    unclear = "unclear"
    sent_application = "sent_application"
    sent_followup = "sent_followup"
    job_alert = "job_alert"   # V3: job-alert digest email


class Job(Base, TimestampMixin):
    """
    One row per job opportunity. Deduped by jd_hash (SHA-256).
    """
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Core job info
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    market: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # NL, SG, Dubai, IN, EU

    # JD content
    jd_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # SHA-256
    jd_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # original scraped text
    jd_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # parsed markdown
    jd_language: Mapped[str] = mapped_column(String(10), default="en")
    # V3: True when the JD is only a snippet from an alert email (LinkedIn/gated cards) —
    # the user should open portal_url for the full description before tailoring.
    has_partial_jd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Detected domain
    industry_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industry_verticals.id"), nullable=True
    )
    function_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("functional_disciplines.id"), nullable=True
    )

    # Application details
    recruiter_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    portal_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[JobSource] = mapped_column(
        SAEnum(JobSource, name="jobsource"), default=JobSource.manual
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="jobstatus"), default=JobStatus.new
    )

    # CV used
    domain_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id"), nullable=True
    )
    # V2: which domain CV feed detected this job + which feed it came from
    detected_domain_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id"), nullable=True, index=True
    )
    source_feed_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_feeds.id", ondelete="SET NULL"), nullable=True
    )
    # V3: the job-alert email this job was extracted from (source=gmail_alert)
    source_email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_threads.id", ondelete="SET NULL"), nullable=True
    )
    tailored_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tailored_cvs.id", use_alter=True, name="fk_jobs_tailored_cv_id"),
        nullable=True
    )

    # Scores
    s1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)          # base fit (master CV)
    s1d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)         # best domain CV fit
    s2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)          # tailored fit
    s3_domain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # integrity vs domain
    s3_master: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # integrity vs master

    # V3: fit against ALL active domain CVs at ingestion time
    # {domain_cv_id: score, ...} — lets the UI show which CV fits best before tailoring
    domain_cv_scores: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # the highest-scoring domain CV for this job (drives Tailor pre-select + Best Fit column)
    best_domain_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id"), nullable=True, index=True
    )

    # Salary
    salary_range_raw: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    salary_expectation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    salary_offered: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Application tracking
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Interview details
    interview_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interview_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interview_format: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # video/phone/onsite
    interviewer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    interviewer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Offer details
    offer_amount: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    offer_currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    offer_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Follow-up tracking
    follow_up_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_count: Mapped[int] = mapped_column(Integer, default=0)

    # Ghosting
    ghosted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Needs HITL flag (genuine recruiter replied)
    needs_hitl: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    email_threads: Mapped[list["EmailThread"]] = relationship(
        back_populates="job", cascade="all, delete-orphan",
        order_by="EmailThread.created_at",
        foreign_keys="EmailThread.job_id",   # disambiguate from jobs.source_email_id
    )


class EmailThread(Base, TimestampMixin):
    """
    Every email in/out for a job application.
    Immutable — only insert, never update.
    """
    __tablename__ = "email_threads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    # Nullable: job-alert digest emails (is_job_alert=True) aren't tied to one job
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True, index=True
    )

    gmail_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    direction: Mapped[EmailDirection] = mapped_column(
        SAEnum(EmailDirection, name="emaildirection"), nullable=False
    )
    classification: Mapped[Optional[EmailClassification]] = mapped_column(
        SAEnum(EmailClassification, name="emailclassification"), nullable=True
    )

    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    from_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    to_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_preview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # first 500 chars

    # Attachments sent (CV/CL)
    cv_pdf_attached: Mapped[bool] = mapped_column(Boolean, default=False)
    cl_pdf_attached: Mapped[bool] = mapped_column(Boolean, default=False)

    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Needs user action (genuine recruiter reply)
    needs_hitl: Mapped[bool] = mapped_column(Boolean, default=False)

    # V3: job-alert digest metadata (set when is_job_alert=True)
    is_job_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jobs_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_saved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    job: Mapped[Optional["Job"]] = relationship(
        back_populates="email_threads", foreign_keys="EmailThread.job_id"
    )
