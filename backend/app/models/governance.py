import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base


class RateLimitLog(Base):
    """One row per rate-limited action; the limiter sums `count` within the window."""
    __tablename__ = "rate_limit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_rate_limit_user_action_window", "user_id", "action", "window_start"),)


class AuditLog(Base):
    """Immutable security/audit trail. Fire-and-forget — never blocks the request."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_audit_user_created", "user_id", "created_at"),
        Index("ix_audit_action_created", "action", "created_at"),
    )
