import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base
from app.models.base import TimestampMixin


class CommunityJobInsight(Base, TimestampMixin):
    """Anonymised, aggregated job-search insights shared across users. NO CV content,
    NO PII — only scores/highlights/patterns. Shown to users only when contributor_count >= 2."""
    __tablename__ = "community_job_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role_normalized: Mapped[str] = mapped_column(String(255), nullable=False)  # lowercased, stripped
    market: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    jd_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    contributor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_s1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_s1d: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_domain_cv_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    jd_highlights: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)       # [{text, votes, category}]
    keyword_patterns: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)    # [{keyword, injection_count, approval_rate}]
    tailoring_patterns: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # [{change_type, approval_count, total_count}]
    response_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_community_company_role", "company", "role_normalized"),
        Index("ix_community_jd_hash", "jd_hash"),
        Index("ix_community_contributor_count", "contributor_count"),
    )


class CommunityContribution(Base):
    """One row per (user, job) contribution — dedupes + powers 'my contributions'."""
    __tablename__ = "community_contributions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    insight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("community_job_insights.id", ondelete="CASCADE"), nullable=False)
    contributed_scores: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contributed_highlights: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contributed_tailoring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
