import uuid
from typing import Optional
from sqlalchemy import String, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base
from app.models.base import TimestampMixin


class IndustryVertical(Base, TimestampMixin):
    """
    Admin-managed master list of industry domains.
    Claude generates profile once, admin approves, then deterministic forever.
    """
    __tablename__ = "industry_verticals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Claude-generated rules (admin-approved)
    detection_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-separated
    emphasis_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # what to highlight
    deemphasis_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # what to tone down
    certifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # relevant certs to surface
    power_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # must-include keywords
    tone_guidance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # writing tone notes
    sample_titles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # common role titles

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class FunctionalDiscipline(Base, TimestampMixin):
    """
    Admin-managed master list of functional PM disciplines.
    """
    __tablename__ = "functional_disciplines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detection_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emphasis_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deemphasis_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    power_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class CountryMaster(Base, TimestampMixin):
    """
    Admin-managed country rules for CV adaptation.
    Rules are deterministic — no AI at runtime.
    """
    __tablename__ = "country_master"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    privacy_law: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # CV adaptation rules
    phone_on_cv: Mapped[bool] = mapped_column(Boolean, default=True)
    remove_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_dob: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_marital_status: Mapped[bool] = mapped_column(Boolean, default=False)
    relocation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lines_to_add: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON array
    lines_to_remove: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    additional_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # free text

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class UserFeed(Base, TimestampMixin):
    """
    Per-user feed configuration (RSS + Apify actors).
    V2: Each feed profile is linked to a domain CV for personalised keywords.
    """
    __tablename__ = "user_feeds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    feed_type: Mapped[str] = mapped_column(String(20), nullable=False)  # rss | apify | brightdata
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url_or_actor: Mapped[str] = mapped_column(Text, nullable=False)
    # V2: human-readable Apify actor name (from the Store picker) — used by the
    # scanner for reliable input-builder matching instead of the opaque actor id
    actor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)

    # Feed-specific settings
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_range_days: Mapped[int] = mapped_column(default=7)

    # V2: Domain CV linkage
    domain_cv_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_cvs.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    search_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_boards: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    # Phase 2: Bright Data feed filters (sub_source, country, experience_level, time_range,
    # domain, date_posted, limit). For brightdata feeds: feed_type='brightdata',
    # url_or_actor = sub-source ('linkedin'|'indeed'); the client maps it to the dataset_id.
    provider_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class UserTargetCompany(Base, TimestampMixin):
    """
    Which companies a user wants to track.
    """
    __tablename__ = "user_target_companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    career_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # NL, SG, Dubai, IN, EU
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform: Mapped[bool] = mapped_column(Boolean, default=False)
