from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import CreditTransactionKind, PlanTier, SubscriptionStatus, UsageKind
from app.schemas.common import ORMModel


class PlanPublic(BaseModel):
    id: str
    name: str
    price_usd_month: int
    monthly_credits: int
    storage_gb: int
    max_video_minutes: int
    max_resolution: str
    watermark: bool
    concurrent_renders: int
    features: list[str]
    is_current: bool = False


class SubscriptionPublic(ORMModel):
    id: uuid.UUID
    plan: PlanTier
    status: SubscriptionStatus
    monthly_credits: int
    storage_limit_bytes: int
    max_video_minutes: int
    max_resolution: str
    watermark_required: bool
    concurrent_renders: int
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    payment_provider: str | None


class UsageSummary(BaseModel):
    period: str
    credits_balance: int
    credits_used: int
    credits_granted: int
    by_kind: dict[str, dict[str, Any]]  # kind -> {quantity: float, credits: float, unit: str}
    storage_used_bytes: int
    storage_limit_bytes: int
    render_minutes: float
    videos_completed: int
    daily: list[dict[str, Any]]


class UsageRecordPublic(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    job_id: uuid.UUID | None
    kind: UsageKind
    quantity: float
    unit: str
    credits: int
    provider: str | None
    model: str | None
    period: str
    created_at: datetime


class CreditTransactionPublic(ORMModel):
    id: uuid.UUID
    kind: CreditTransactionKind
    amount: int
    balance_after: int
    description: str | None
    project_id: uuid.UUID | None
    job_id: uuid.UUID | None
    reference: str | None
    created_at: datetime


class ChangePlanRequest(BaseModel):
    plan: PlanTier


class CheckoutRequest(BaseModel):
    plan: PlanTier
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str | None
    mode: str  # "stripe" | "manual"
    message: str


class CreditPurchaseRequest(BaseModel):
    credits: int = Field(ge=100, le=1_000_000)


class CostEstimate(BaseModel):
    credits: int
    breakdown: dict[str, int]
    balance: int
    sufficient: bool
