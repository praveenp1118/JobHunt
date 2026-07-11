import uuid
from enum import Enum
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, Enum as SAEnum, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.database import Base
from app.models.base import TimestampMixin


class CVStatus(str, Enum):
    active = "active"
    stale = "stale"                 # master CV updated, needs regeneration
    review_required = "review_required"  # S3 in amber zone (85-90%)
    blocked = "blocked"             # S3 below 85%, cannot send
    regenerating = "regenerating"   # currently being regenerated


class ChangeType(str, Enum):
    rephrase = "rephrase"
    keyword_injection = "keyword_injection"
    reorder = "reorder"
    deselect = "deselect"           # remove a bullet


class ChangeStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    approved_edited = "approved_edited"  # user modified before approving
    rejected = "rejected"


class MasterCV(Base, TimestampMixin):
    """
    The single source of truth per user. Always stored as markdown.
    """
    __tablename__ = "master_cvs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Hybrid-RAG: structured CV essence (computed once per upload/update, used by Stage 2)
    essence_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    essence_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    essence_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    versions: Mapped[list["MasterCVVersion"]] = relationship(
        back_populates="master_cv", cascade="all, delete-orphan",
        order_by="MasterCVVersion.version.desc()"
    )
    domain_cvs: Mapped[list["DomainCV"]] = relationship(
        back_populates="master_cv", cascade="all, delete-orphan"
    )


class MasterCVVersion(Base):
    """
    Immutable version history for master CV.
    """
    __tablename__ = "master_cv_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    master_cv_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("master_cvs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    from datetime import datetime
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    master_cv: Mapped["MasterCV"] = relationship(back_populates="versions")


class DomainCV(Base, TimestampMixin):
    """
    One per Industry × Function × Country per user.
    Always derived from master CV — never from another domain CV.
    """
    __tablename__ = "domain_cvs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    master_cv_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("master_cvs.id", ondelete="CASCADE"),
        nullable=False
    )
    industry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("industry_verticals.id"),
        nullable=False
    )
    function_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("functional_disciplines.id"),
        nullable=False
    )
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)

    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[CVStatus] = mapped_column(
        SAEnum(CVStatus, name="cvstatus"), default=CVStatus.active
    )

    # S3 scores (vs domain base and vs master)
    s3_domain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    s3_master: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Hybrid-RAG: structured essence (incl. domain extras), computed on apply
    essence_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    essence_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Storage
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    master_cv: Mapped["MasterCV"] = relationship(back_populates="domain_cvs")
    versions: Mapped[list["DomainCVVersion"]] = relationship(
        back_populates="domain_cv", cascade="all, delete-orphan"
    )
    tailored_cvs: Mapped[list["TailoredCV"]] = relationship(
        back_populates="domain_cv"
    )


class DomainCVVersion(Base):
    """Immutable version history for domain CVs."""
    __tablename__ = "domain_cv_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    domain_cv_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_domain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    s3_master: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    from datetime import datetime
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    domain_cv: Mapped["DomainCV"] = relationship(back_populates="versions")


class TailoredCV(Base, TimestampMixin):
    """
    Per-job tailored CV generated from a domain CV.
    Stored as markdown. PDF generated on-demand at send time.
    """
    __tablename__ = "tailored_cvs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    domain_cv_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id"),
        nullable=False
    )

    cv_md: Mapped[str] = mapped_column(Text, nullable=False)
    cover_letter_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_draft: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scores
    s2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)         # tailored vs JD
    s3_domain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # vs domain CV
    s3_master: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # vs master CV (the gate)

    # Cover letter template used
    cl_template_used: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # PDF paths (generated on send)
    cv_pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cl_pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Draft persistence (v4) — restore the tailored draft on return so Claude only
    #    re-runs on an explicit "Re-tailor". ──
    # 'generated' = change log ready, cv_md still empty (not applied yet);
    # 'applied'   = cv_md + S3 filled (a full restore is possible).
    status: Mapped[str] = mapped_column(
        String(20), default="generated", server_default="generated", nullable=False
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Staleness snapshots (FLAG only, never auto-re-run): domain CV version + JD hash at tailor time.
    base_domain_cv_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jd_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    domain_cv: Mapped["DomainCV"] = relationship(back_populates="tailored_cvs")
    change_logs: Mapped[list["ChangeLog"]] = relationship(
        back_populates="tailored_cv", cascade="all, delete-orphan"
    )


class ChangeLog(Base, TimestampMixin):
    """
    Every proposed change Claude makes to a CV.
    User approves, rejects, or edits inline.
    Approved changes recompute S3 after Generate.
    """
    __tablename__ = "change_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    tailored_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tailored_cvs.id", ondelete="CASCADE"),
        nullable=True
    )
    domain_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id", ondelete="CASCADE"),
        nullable=True
    )

    change_type: Mapped[ChangeType] = mapped_column(
        SAEnum(ChangeType, name="changetype"), nullable=False
    )
    section: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proposed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # what was actually used
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[ChangeStatus] = mapped_column(
        SAEnum(ChangeStatus, name="changestatus"), default=ChangeStatus.pending
    )

    # Relationships
    tailored_cv: Mapped[Optional["TailoredCV"]] = relationship(back_populates="change_logs")
