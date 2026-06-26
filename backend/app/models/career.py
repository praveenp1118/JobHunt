import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base
from app.models.base import TimestampMixin


class CareerAnalysis(Base, TimestampMixin):
    """Cached career-gap analysis — one per (user, filter combination), 7-day TTL."""
    __tablename__ = "career_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    readiness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    keywords_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skills_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    experience_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    certifications_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    analysis_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    jd_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_analysed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Per-filter caching (one analysis per filter combination)
    filter_hash: Mapped[str] = mapped_column(String(100), default="all", nullable=False)
    filter_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    filter_feed_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    filter_domain_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    filter_market: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    filter_label: Mapped[str] = mapped_column(String(100), default="All jobs", nullable=False)

    __table_args__ = (Index("ix_career_analysis_user_filter", "user_id", "filter_hash", unique=True),)


class CareerRoadmapItem(Base):
    __tablename__ = "career_roadmap_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filter_hash: Mapped[str] = mapped_column(String(100), default="all", nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # keyword/skill/cert/project/experience
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    impact_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    timeframe: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # this_week/this_month/3_months
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class CareerQuestion(Base):
    __tablename__ = "career_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(String(50), nullable=False)
    answer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (Index("ix_career_q_user_key", "user_id", "question_key", unique=True),)


class CommunityCareerInsight(Base, TimestampMixin):
    __tablename__ = "community_career_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # "Head of Product · AI · NL"
    insight_type: Mapped[str] = mapped_column(String(30), nullable=False)  # keyword/skill/cert/project
    insight_value: Mapped[str] = mapped_column(String(255), nullable=False)
    frequency_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contributor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_stories: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
