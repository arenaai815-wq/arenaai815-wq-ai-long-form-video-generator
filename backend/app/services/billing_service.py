"""Credits, usage metering and subscription limits.

Sync implementation (used by workers) + thin async wrappers (used by the API).
The credit ledger is append-only; `users.credits_balance` is the cached balance
and is always updated in the same transaction as the ledger row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import InsufficientCreditsError
from app.models.billing import PLAN_CATALOG, CreditTransaction, Subscription, UsageRecord
from app.models.enums import CreditTransactionKind, PlanTier, SubscriptionStatus, UsageKind
from app.models.user import User
from app.providers.base import UsageMetrics


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


# ---------------------------------------------------------------- cost model


def credits_for_usage(kind: UsageKind, quantity: float) -> int:
    s = settings
    if kind == UsageKind.RESEARCH:
        return s.credit_cost_research
    if kind == UsageKind.SCRIPT:
        return max(1, int(round(quantity * s.credit_cost_script_per_minute)))  # quantity = minutes
    if kind == UsageKind.TTS_CHARACTERS:
        return max(1, int(-(-quantity // 1000) * s.credit_cost_tts_per_1k_chars))
    if kind == UsageKind.IMAGE_GENERATION:
        return int(quantity) * s.credit_cost_image
    if kind == UsageKind.VIDEO_GENERATION:
        return int(max(1, quantity)) * s.credit_cost_video_clip
    if kind == UsageKind.RENDER_SECONDS:
        return max(1, int(-(-quantity // 60) * s.credit_cost_render_per_minute))
    if kind == UsageKind.LLM_TOKENS:
        return int(quantity // 4000)  # bundled into research/script pricing
    return 0


def estimate_pipeline_cost(*, duration_minutes: int, scene_count: int, ai_video_ratio: float = 0.0, stages: list[str] | None = None) -> dict[str, int]:
    stages = stages or ["research", "script", "scenes", "voiceover", "visuals", "captions", "render"]
    words = duration_minutes * 150
    chars = words * 5.5
    breakdown: dict[str, int] = {}
    if "research" in stages:
        breakdown["research"] = credits_for_usage(UsageKind.RESEARCH, 1)
    if "script" in stages:
        breakdown["script"] = credits_for_usage(UsageKind.SCRIPT, duration_minutes)
    if "voiceover" in stages:
        breakdown["voiceover"] = credits_for_usage(UsageKind.TTS_CHARACTERS, chars)
    if "visuals" in stages:
        video_scenes = int(scene_count * ai_video_ratio)
        breakdown["images"] = credits_for_usage(UsageKind.IMAGE_GENERATION, scene_count - video_scenes)
        if video_scenes:
            breakdown["video_clips"] = credits_for_usage(UsageKind.VIDEO_GENERATION, video_scenes)
    if "render" in stages:
        breakdown["render"] = credits_for_usage(UsageKind.RENDER_SECONDS, duration_minutes * 60)
    return breakdown


# ---------------------------------------------------------------- sync API (workers)


def ensure_subscription_sync(db: Session, user: User) -> Subscription:
    sub = db.execute(select(Subscription).where(Subscription.user_id == user.id)).scalar_one_or_none()
    if sub is None:
        sub = _new_subscription(user.id, PlanTier.FREE)
        db.add(sub)
        db.flush()
    return sub


def _new_subscription(user_id: uuid.UUID, plan: PlanTier) -> Subscription:
    cat = PLAN_CATALOG[plan.value]
    now = datetime.now(UTC)
    return Subscription(
        user_id=user_id,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        monthly_credits=cat["monthly_credits"],
        storage_limit_bytes=cat["storage_gb"] * 1024**3,
        max_video_minutes=cat["max_video_minutes"],
        max_resolution=cat["max_resolution"],
        watermark_required=cat["watermark"],
        concurrent_renders=cat["concurrent_renders"],
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )


def apply_plan(sub: Subscription, plan: PlanTier) -> None:
    cat = PLAN_CATALOG[plan.value]
    sub.plan = plan
    sub.monthly_credits = cat["monthly_credits"]
    sub.storage_limit_bytes = cat["storage_gb"] * 1024**3
    sub.max_video_minutes = cat["max_video_minutes"]
    sub.max_resolution = cat["max_resolution"]
    sub.watermark_required = cat["watermark"]
    sub.concurrent_renders = cat["concurrent_renders"]


def add_credits_sync(
    db: Session,
    user: User,
    amount: int,
    kind: CreditTransactionKind,
    *,
    description: str | None = None,
    reference: str | None = None,
    project_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
) -> CreditTransaction:
    if reference:
        existing = db.execute(select(CreditTransaction).where(CreditTransaction.reference == reference)).scalar_one_or_none()
        if existing:
            return existing
    # Atomic balance update guards against concurrent workers double spending.
    db.execute(update(User).where(User.id == user.id).values(credits_balance=User.credits_balance + amount))
    db.flush()
    db.refresh(user, attribute_names=["credits_balance"])
    tx = CreditTransaction(
        user_id=user.id,
        kind=kind,
        amount=amount,
        balance_after=user.credits_balance,
        description=description,
        reference=reference,
        project_id=project_id,
        job_id=job_id,
    )
    db.add(tx)
    db.flush()
    return tx


def charge_credits_sync(
    db: Session,
    user: User,
    amount: int,
    *,
    description: str,
    reference: str | None = None,
    project_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    allow_negative: bool = False,
) -> CreditTransaction | None:
    if amount <= 0:
        return None
    db.refresh(user, attribute_names=["credits_balance"])
    if user.credits_balance < amount and not allow_negative:
        raise InsufficientCreditsError(
            f"This action needs {amount} credits but you have {user.credits_balance}.",
            details={"required": amount, "balance": user.credits_balance},
        )
    return add_credits_sync(
        db, user, -amount, CreditTransactionKind.CONSUMPTION,
        description=description, reference=reference, project_id=project_id, job_id=job_id,
    )


def record_usage_sync(
    db: Session,
    user: User,
    kind: UsageKind,
    quantity: float,
    unit: str,
    *,
    metrics: UsageMetrics | None = None,
    project_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    charge: bool = True,
    reference: str | None = None,
) -> UsageRecord:
    credits = credits_for_usage(kind, quantity) if charge else 0
    rec = UsageRecord(
        user_id=user.id,
        project_id=project_id,
        job_id=job_id,
        kind=kind,
        quantity=float(quantity),
        unit=unit,
        credits=credits,
        provider=metrics.provider if metrics else None,
        model=metrics.model if metrics else None,
        period=current_period(),
        metadata_={"latency_ms": metrics.latency_ms, **({"raw": metrics.raw} if metrics and metrics.raw else {})} if metrics else {},
    )
    db.add(rec)
    if credits:
        # Usage is recorded *after* work is done, so we allow the balance to dip below zero rather than
        # discarding produced work; pre-flight checks (`assert_can_afford`) prevent runaway spending.
        charge_credits_sync(
            db, user, credits,
            description=f"{kind.value}: {quantity:g} {unit}",
            reference=reference, project_id=project_id, job_id=job_id, allow_negative=True,
        )
    db.flush()
    return rec


def assert_can_afford_sync(db: Session, user: User, credits: int) -> None:
    db.refresh(user, attribute_names=["credits_balance"])
    if user.credits_balance < credits:
        raise InsufficientCreditsError(
            f"Insufficient credits: need {credits}, have {user.credits_balance}.",
            details={"required": credits, "balance": user.credits_balance},
        )


# ---------------------------------------------------------------- async API (FastAPI)


async def ensure_subscription(db: AsyncSession, user: User) -> Subscription:
    sub = (await db.execute(select(Subscription).where(Subscription.user_id == user.id))).scalar_one_or_none()
    if sub is None:
        sub = _new_subscription(user.id, PlanTier.FREE)
        db.add(sub)
        await db.flush()
    return sub


async def add_credits(
    db: AsyncSession,
    user: User,
    amount: int,
    kind: CreditTransactionKind,
    *,
    description: str | None = None,
    reference: str | None = None,
) -> CreditTransaction:
    if reference:
        existing = (await db.execute(select(CreditTransaction).where(CreditTransaction.reference == reference))).scalar_one_or_none()
        if existing:
            return existing
    await db.execute(update(User).where(User.id == user.id).values(credits_balance=User.credits_balance + amount))
    await db.flush()
    await db.refresh(user, attribute_names=["credits_balance"])
    tx = CreditTransaction(
        user_id=user.id, kind=kind, amount=amount, balance_after=user.credits_balance,
        description=description, reference=reference,
    )
    db.add(tx)
    await db.flush()
    return tx


async def assert_can_afford(db: AsyncSession, user: User, credits: int) -> None:
    await db.refresh(user, attribute_names=["credits_balance"])
    if user.credits_balance < credits:
        raise InsufficientCreditsError(
            f"Insufficient credits: this needs about {credits} credits and you have {user.credits_balance}.",
            details={"required": credits, "balance": user.credits_balance},
        )
