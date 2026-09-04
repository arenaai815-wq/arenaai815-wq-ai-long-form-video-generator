from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import TERMINAL_STATES, ProjectStatus, UsageKind, dimensions_for
from app.models.job import RenderJob
from app.models.media import MediaAsset
from app.schemas.job import RenderJobPublic, RenderRequest
from app.services.billing_service import assert_can_afford, credits_for_usage, ensure_subscription
from app.services.job_service import create_render_job
from app.services.media_service import url_for
from app.services.timeline_service import get_or_create_timeline

router = APIRouter()


async def _public(db: DB, r: RenderJob) -> RenderJobPublic:
    p = RenderJobPublic.model_validate(r)
    if r.output_asset_id:
        a = await db.get(MediaAsset, r.output_asset_id)
        if a:
            p.output_url = url_for(a.storage_key, filename=a.filename)
    return p


@router.post("/projects/{project_id}/render", response_model=RenderJobPublic, status_code=status.HTTP_202_ACCEPTED, summary="Queue a preview or final render")
@limiter.limit("10/minute")
async def start_render(request: Request, body: RenderRequest, project: OwnedProject, user: CurrentUser, db: DB) -> RenderJobPublic:
    sub = await ensure_subscription(db, user)
    tl = await db.run_sync(lambda s: get_or_create_timeline(s, project))
    if not any(t.get("clips") for t in (tl.data or {}).get("tracks", [])):
        raise ValidationError("Nothing to render yet - build the storyboard first")
    active = (await db.execute(select(func.count()).select_from(RenderJob).where(RenderJob.user_id == user.id, RenderJob.state.not_in(list(TERMINAL_STATES))))).scalar_one()
    if active >= sub.concurrent_renders:
        raise ValidationError(f"Your plan allows {sub.concurrent_renders} concurrent render(s). Wait for the current render to finish.")
    resolution = body.resolution or project.resolution
    order = ["720p", "1080p", "1440p", "4k"]
    if order.index(resolution) > order.index(sub.max_resolution):
        raise ValidationError(f"{resolution} export requires a higher plan (your max: {sub.max_resolution}).")
    w, h = dimensions_for(project.aspect_ratio, resolution)
    duration = float(tl.duration_seconds or project.estimated_duration_seconds or 60)
    if body.range_start is not None or body.range_end is not None:
        duration = max(1.0, float(body.range_end or duration) - float(body.range_start or 0))
    if not body.preview:
        await assert_can_afford(db, user, credits_for_usage(UsageKind.RENDER_SECONDS, duration))
    caps = (project.settings or {}).get("captions") or {}
    burn = body.burn_captions if body.burn_captions is not None else bool(caps.get("burn_in", True))
    wm_enabled = bool(((project.settings or {}).get("watermark") or {}).get("enabled"))
    include_wm = body.include_watermark if body.include_watermark is not None else wm_enabled
    include_wm = include_wm or sub.watermark_required  # free plan always watermarks
    job, created = await create_render_job(
        db, project_id=project.id, user_id=user.id, width=w, height=h, fps=body.fps or 30, is_preview=body.preview,
        burn_captions=burn, include_watermark=include_wm, timeline_version=tl.version, timeline_snapshot=tl.data,
        params={"range_start": body.range_start, "range_end": body.range_end, "resolution": resolution},
        idempotency_key=body.idempotency_key, credits_reserved=0 if body.preview else credits_for_usage(UsageKind.RENDER_SECONDS, duration),
    )
    if created:
        project.status = ProjectStatus.RENDERING
        await db.commit()
        from workers.tasks.render import run_render_job

        res = run_render_job.apply_async(args=[str(job.id)], queue="render")
        job.celery_task_id = res.id
    return await _public(db, job)


@router.get("/projects/{project_id}/renders", response_model=list[RenderJobPublic])
async def list_renders(project: OwnedProject, db: DB, limit: int = Query(20, le=100)) -> list[RenderJobPublic]:
    rows = (await db.execute(select(RenderJob).where(RenderJob.project_id == project.id).order_by(RenderJob.created_at.desc()).limit(limit))).scalars().all()
    return [await _public(db, r) for r in rows]


@router.get("/projects/{project_id}/renders/{render_id}", response_model=RenderJobPublic)
async def get_render(render_id: uuid.UUID, project: OwnedProject, db: DB) -> RenderJobPublic:
    r = await db.get(RenderJob, render_id)
    if r is None or r.project_id != project.id:
        raise NotFoundError("Render not found")
    return await _public(db, r)


@router.get("/projects/{project_id}/export", summary="Signed download URL for the latest final render")
async def export_latest(project: OwnedProject, db: DB) -> dict:
    if not project.final_video_asset_id:
        raise NotFoundError("No final render yet")
    a = await db.get(MediaAsset, project.final_video_asset_id)
    if a is None:
        raise NotFoundError("Rendered file missing")
    return {
        "asset_id": str(a.id),
        "url": url_for(a.storage_key, filename=a.filename, expires=settings.signed_url_expire_seconds),
        "filename": a.filename,
        "size_bytes": a.size_bytes,
        "duration_seconds": a.duration_seconds,
        "width": a.width,
        "height": a.height,
        "thumbnail_url": url_for(a.thumbnail_key),
    }
