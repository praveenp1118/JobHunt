import uuid
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base
from app.models.base import TimestampMixin

DEFAULT_NEVER_MODIFY = ["EDUCATION", "CERTIFICATIONS"]
DEFAULT_SECTION_ORDER = ["SUMMARY", "EXPERIENCE", "EDUCATION", "CERTIFICATIONS"]


class CVTemplate(Base, TimestampMixin):
    """One global CV template per user — aesthetic (PDF) + content (tailor prompt) rules."""
    __tablename__ = "cv_template"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # ── Aesthetic rules (PDF) ──
    font_family: Mapped[str] = mapped_column(String(50), default="Calibri", nullable=False)
    font_size: Mapped[int] = mapped_column(Integer, default=11, nullable=False)
    heading_font_family: Mapped[str] = mapped_column(String(50), default="Calibri", nullable=False)
    heading_font_size: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    heading_bold: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    margin_size: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)  # narrow/normal/wide
    line_spacing: Mapped[float] = mapped_column(Float, default=1.15, nullable=False)
    bullet_style: Mapped[str] = mapped_column(String(10), default="•", nullable=False)  # •/–/▪/none
    accent_color: Mapped[str] = mapped_column(String(7), default="#1a1a1a", nullable=False)

    # ── Page rules ──
    max_pages: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    overflow_action: Mapped[str] = mapped_column(String(20), default="warn", nullable=False)  # warn/auto_trim

    # ── Content rules (tailor prompt) ──
    never_modify_sections: Mapped[list] = mapped_column(JSONB, default=lambda: list(DEFAULT_NEVER_MODIFY), nullable=False)
    section_order: Mapped[list] = mapped_column(JSONB, default=lambda: list(DEFAULT_SECTION_ORDER), nullable=False)
    max_words: Mapped[int] = mapped_column(Integer, default=600, nullable=False)  # = max_pages * 300


class DomainCVTemplateOverride(Base, TimestampMixin):
    """Per-domain-CV overrides. All fields nullable — null means "use the global template"."""
    __tablename__ = "domain_cv_template_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_cv_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id", ondelete="CASCADE"), unique=True, nullable=False)

    font_family: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    font_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overflow_action: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    never_modify_sections: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    section_order: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    max_words: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
