import uuid
from enum import Enum
from typing import Optional
from sqlalchemy import String, Integer, Text, ForeignKey, Enum as SAEnum, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TransactionType(str, Enum):
    debit = "debit"
    topup = "topup"
    gift = "gift"
    refund = "refund"


class Wallet(Base, TimestampMixin):
    """
    One wallet per user. Balance stored in paise (₹1 = 100 paise).
    """
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True
    )
    balance_paise: Mapped[int] = mapped_column(BigInteger, default=2000)  # ₹20 starter gift

    # Relationships
    user: Mapped["User"] = relationship(back_populates="wallet")  # noqa: F821
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class WalletTransaction(Base):
    """
    Immutable ledger. Never update — only insert.
    """
    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transactiontype"), nullable=False
    )
    action_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)  # positive for credit, negative for debit
    balance_after_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True  # which job this action was for
    )
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    from datetime import datetime
    from sqlalchemy import DateTime, func
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    wallet: Mapped["Wallet"] = relationship(back_populates="transactions")


class ActionPricing(Base, TimestampMixin):
    """
    Admin-configurable pricing for Wallet plan users.
    Default plan users are not charged.
    """
    __tablename__ = "action_pricing"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    action_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)  # ₹1 = 100 paise
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
