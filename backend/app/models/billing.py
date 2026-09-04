from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CreditTransactionKind, PlanTier, SubscriptionStatus, UsageKind

if TYPE_CHECKING:
    from app.models.user import User


PLAN_CATALOG: dict[str, dict] = {
    PlanTier.FREE.value: {
        "name": "Free",
        "price_usd_month": 0,
        "monthly_credits": 500,
        "storage_gb": 2,
        "max_video_minutes": 10,
        "max_resolution": "1080p",
        "watermark": True,
        "concurrent_renders": 1,
        "features": ["AI research & script", "Mock/limited providers", "720p/1080p export"],
    },
    PlanTier.CREATOR.value: {
        "name": "Creator",
        "price_usd_month": 29,
        "monthly_credits": 5000,
        "storage_gb": 50,
        "max_video_minutes": 30,
        "max_resolution": "1080p",
        "watermark": False,
        "concurrent_renders": 2,
        "features": ["All Free features", "No watermark", "Premium voices", "Stock footage"],
    },
    PlanTier.PRO.value: {
        "name": "Pro",
        "price_usd_month": 79,
        "monthly_credits": 15000,
        "storage_gb": 250,
        "max_video_minutes": 60,
        "max_resolution": "4k",
        "watermark": False,
        "concurrent_renders": 4,
        "features": ["All Creator features", "4K export", "AI video clips", "Priority rendering"],
    },
    PlanTier.STUDIO.value: {
        "name": "Studio",
        "price_usd_month": 199,
        "monthly_credits": 50000,
        "storage_gb": 1000,
        "max_video_minutes": 180,
        "max_resolution": "4k",
        "watermark": False,
        "concurrent_renders": 10,
        "features": ["All Pro features", "Team seats", "API access", "Dedicated workers"],
    },
}


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    plan: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier", native_enum=False, length=16), default=PlanTier.FREE, nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False, length=16),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )
    monthly_credits: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    storage_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=2 * 1024**3, nullable=False)
    max_video_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_resolution: Mapped[str] = mapped_column(String(10), default="1080p", nullable=False)
    watermark_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    concurrent_renders: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Payment-provider references (Stripe or otherwise). No secrets.
    payment_provider: Mapped[str | None] = mapped_column(String(30))
    external_customer_id: Mapped[str | None] = mapped_column(String(120), index=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(120), index=True)
    external_price_id: Mapped[str | None] = mapped_column(String(120))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="subscription")


class UsageRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Fine-grained metering. Aggregated by period for the billing page."""

    __tablename__ = "usage_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    kind: Mapped[UsageKind] = mapped_column(
        Enum(UsageKind, name="usage_kind", native_enum=False, length=32), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # tokens, chars, images, seconds, bytes
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(120))
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM for fast aggregation
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="usage_records")

    __table_args__ = (
        Index("ix_usage_records_user_id_period_kind", "user_id", "period", "kind"),
        Index("ix_usage_records_project_id", "project_id"),
    )


class CreditTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only ledger. `balance_after` allows auditing without recomputing."""

    __tablename__ = "credit_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[CreditTransactionKind] = mapped_column(
        Enum(CreditTransactionKind, name="credit_tx_kind", native_enum=False, length=32), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # positive = credit, negative = debit
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    reference: Mapped[str | None] = mapped_column(String(120), index=True)  # idempotency / external id
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="credit_transactions")

    __table_args__ = (Index("ix_credit_transactions_user_id_created_at", "user_id", "created_at"),)
