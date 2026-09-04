"""Usage metering & credit ledger endpoints (feeds the dashboard and Billing/Usage page)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.models.billing import CreditTransaction, UsageRecord
from app.models.enums import CreditTransactionKind, JobState, UsageKind
from app.models.job import RenderJob
from app.models.project import Project
from app.schemas.billing import CreditTransactionPublic, UsageRecordPublic, UsageSummary
from app.schemas.common import Page
from app.services.billing_service import current_period, ensure_subscription

router = APIRouter()

UNITS = {
    UsageKind.LLM_TOKENS: "tokens", UsageKind.RESEARCH: "runs", UsageKind.SCRIPT: "minutes", UsageKind.TTS_CHARACTERS: "characters",
    UsageKind.IMAGE_GENERATION: "images", UsageKind.VIDEO_GENERATION: "clips", UsageKind.STT_SECONDS: "seconds",
    UsageKind.RENDER_SECONDS: "seconds", UsageKind.STORAGE_BYTES: "bytes",
}


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(user: CurrentUser, db: DB, period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")) -> UsageSummary:
    period = period or current_period()
    sub = await ensure_subscription(db, user)
    rows = (await db.execute(select(UsageRecord.kind, func.sum(UsageRecord.quantity), func.sum(UsageRecord.credits)).where(UsageRecord.user_id == user.id, UsageRecord.period == period).group_by(UsageRecord.kind))).all()
    by_kind = {k.value: {"quantity": float(q or 0), "credits": float(c or 0), "unit": UNITS.get(k, "")} for k, q, c in rows}
    for k in UsageKind:
        by_kind.setdefault(k.value, {"quantity": 0.0, "credits": 0.0, "unit": UNITS.get(k, "")})
    start = datetime.strptime(period, "%Y-%m").replace(tzinfo=UTC)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    used = (await db.execute(select(func.coalesce(func.sum(-CreditTransaction.amount), 0)).where(CreditTransaction.user_id == user.id, CreditTransaction.kind == CreditTransactionKind.CONSUMPTION, CreditTransaction.created_at >= start, CreditTransaction.created_at < end))).scalar_one()
    granted = (await db.execute(select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(CreditTransaction.user_id == user.id, CreditTransaction.amount > 0, CreditTransaction.created_at >= start, CreditTransaction.created_at < end))).scalar_one()
    render_seconds = by_kind[UsageKind.RENDER_SECONDS.value]["quantity"]
    videos = (await db.execute(select(func.count()).select_from(RenderJob).where(RenderJob.user_id == user.id, RenderJob.state == JobState.COMPLETED, RenderJob.is_preview.is_(False), RenderJob.finished_at >= start, RenderJob.finished_at < end))).scalar_one()
    day = func.date_trunc("day", UsageRecord.created_at).label("day")
    daily_rows = (await db.execute(select(day, func.sum(UsageRecord.credits)).where(UsageRecord.user_id == user.id, UsageRecord.period == period).group_by(day).order_by(day))).all()
    daily = [{"date": d.date().isoformat(), "credits": int(c or 0)} for d, c in daily_rows]
    return UsageSummary(period=period, credits_balance=user.credits_balance, credits_used=int(used), credits_granted=int(granted), by_kind=by_kind, storage_used_bytes=user.storage_bytes_used, storage_limit_bytes=sub.storage_limit_bytes, render_minutes=round(render_seconds / 60, 2), videos_completed=int(videos), daily=daily)


@router.get("/records", response_model=Page[UsageRecordPublic])
async def usage_records(user: CurrentUser, db: DB, kind: UsageKind | None = None, project_id: uuid.UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[UsageRecordPublic]:
    stmt = select(UsageRecord).where(UsageRecord.user_id == user.id)
    if kind:
        stmt = stmt.where(UsageRecord.kind == kind)
    if project_id:
        stmt = stmt.where(UsageRecord.project_id == project_id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(UsageRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[UsageRecordPublic.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/credits", response_model=Page[CreditTransactionPublic], summary="Credit ledger")
async def credit_ledger(user: CurrentUser, db: DB, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> Page[CreditTransactionPublic]:
    stmt = select(CreditTransaction).where(CreditTransaction.user_id == user.id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(CreditTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[CreditTransactionPublic.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/projects", summary="Credits spent per project (current period)")
async def usage_by_project(user: CurrentUser, db: DB, period: str | None = None) -> list[dict]:
    period = period or current_period()
    rows = (await db.execute(select(UsageRecord.project_id, func.sum(UsageRecord.credits)).where(UsageRecord.user_id == user.id, UsageRecord.period == period, UsageRecord.project_id.is_not(None)).group_by(UsageRecord.project_id))).all()
    ids = [pid for pid, _ in rows]
    titles = {p.id: p.title for p in (await db.execute(select(Project).where(Project.id.in_(ids)))).scalars()} if ids else {}
    return sorted(({"project_id": str(pid), "title": titles.get(pid, "Deleted project"), "credits": int(c or 0)} for pid, c in rows), key=lambda r: -r["credits"])
