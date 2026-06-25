import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base


class APIUsageLog(Base):
    """One row per external API call (Anthropic message / Apify actor run) — powers the
    Settings → API Usage tab (30-day rolling token + cost visibility)."""
    __tablename__ = "api_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)            # anthropic / apify
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)         # generate_tailor_package etc
    category: Mapped[str] = mapped_column(String(30), nullable=False)            # tailoring/scoring/domain_cv/scanner/gmail/other
    entity_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)   # job/cv/scan/alert/master_cv
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # "Adyen · Head of Product"
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_cost_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)      # Apify
    runs_requested: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runs_returned: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jobs_saved: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_summary: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # "6 changes generated"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_api_usage_user_created", "user_id", "created_at"),
        Index("ix_api_usage_user_provider", "user_id", "provider"),
        Index("ix_api_usage_user_category", "user_id", "category"),
    )
