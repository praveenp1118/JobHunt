"""
Access-control models for the invite-or-pay registration gate.

A new account is INERT (can log in, can't use paid/Claude features) until it is
entitled — either by redeeming a single-use InvitationKey (grants N free days) or
by subscribing via Stripe. Entitlement itself is stored on the existing
`users.subscription_status` / `users.subscription_end` columns (reused from the
Stripe work) plus `users.entitlement_source` ('invite' | 'stripe' | None).

  - InvitationKey  → table `invitation_keys` (single-use redeemable keys)
  - ExtensionRequest → table `extension_requests` (in-app queue for more free time)
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped

from app.database import Base
from app.models.base import TimestampMixin


class InvitationKey(Base, TimestampMixin):
    """
    A single-use invitation key. Redeeming grants the redeemer `grants_days` of
    free access (subscription_status=active, subscription_end=now+grants_days,
    entitlement_source='invite').

    A key is INVALID if it is redeemed (redeemed_by set) OR revoked (is_revoked)
    OR past its redemption deadline (key_expires_at, when set).
    """
    __tablename__ = "invitation_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # How many free days redeeming this key grants.
    grants_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # Redemption deadline. NULL = never expires (can be redeemed any time).
    key_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Single-use redemption bookkeeping.
    redeemed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ExtensionRequest(Base, TimestampMixin):
    """
    An invited user's request for more free time after their period lapses. The
    in-app queue (these rows) is the source of truth; an admin email is a
    best-effort notification on top. Granting bumps the user's subscription_end.
    """
    __tablename__ = "extension_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    # pending / granted / denied
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
