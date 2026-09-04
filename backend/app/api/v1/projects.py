from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import JobType, ProjectStatus, TERMINAL_STATES
from app.models.job import GenerationJob, RenderJob
from app.models.media import Caption, MediaAsset, Voiceover
from app.models.project import Project
from app.models.scene import Scene
from app.models.script import Script
from app.schemas.billing import CostEstimate
from app.schemas.common import Message, Page
from app.schemas.job import JobPublic, PipelineRequest
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectSettings, ProjectStats, ProjectSummary, ProjectUpdate
from app.services.billing_service import assert_can_afford, estimate_pipeline_cost
from app.services.job_service import active_job_for_project, create_generation_job
from app.services.media_service import url_for

router = APIRouter()


async def _summary(db: DB, p: Project, with_job: bool = True) -> ProjectSummary:
    thumb_url = final_url = None
    if p.thumbnail_asset_id:
        a = await db.get(MediaAsset, p.thumbnail_asset_id)
        if a:
            thumb_url = url_for(a.thumbnail_key or a.storage_key)
    if p.final_video_asset_id:
        a = await db.get(MediaAsset, p.final_video_asset_id)
        if a:
            final_url = url_for(a.storage_key, filename=a.filename)
            if not thumb_url and a.thumbnail_key:
                thumb_url = url_for(a.thumbnail_key)
    data = ProjectSummary.model_validate(p)
    data.thumbnail_url = thumb_url
    data.final_video_url = final_url
    if with_job:
        data.active_job = await active_job_for_project(db, p.id)
    return data


async def _detail(db: DB, p: Project) -> ProjectDetail:
    base = await _summary(db, p)
    scene_count = (await db.execute(select(func.count()).select_from(Scene).where(Scene.project_id == p.id))).scalar_one()
    voiced = (await db.execute(select(func.count()).select_from(Scene).where(Scene.project_id == p.id, Scene.voiceover_id.is_not(None)))).scalar_one()
    visualized = (await db.execute(select(func.count()).select_from(Scene).where(Scene.project_id == p.id, Scene.visual_asset_id.is_not(None)))).scalar_one()
    script = (await db.execute(select(Script).where(Script.project_id == p.id, Script.is_current.is_(True)))).scalars().first()
    has_captions = (await db.execute(select(func.count()).select_from(Caption).where(Caption.project_id == p.id, Caption.is_current.is_(True)))).scalar_one() > 0
    renders = (await db.execute(select(func.count()).select_from(RenderJob).where(RenderJob.project_id == p.id))).scalar_one()
    detail = ProjectDetail(
        **base.model_dump(),
        description=p.description,
        target_audience=p.target_audience,
        settings=p.settings or {},
        thumbnail_asset_id=p.thumbnail_asset_id,
        final_video_asset_id=p.final_video_asset_id,
        last_opened_at=p.last_opened_at,
        counts={"scenes": scene_count, "voiced": voiced, "visualized": visualized, "renders": renders, "script_words": script.word_count if script else 0},
        pipeline={
            "research": bool(p.research and p.research.sections),
            "script": bool(script and script.word_count),
            "scenes": scene_count > 0,
            "voiceover": scene_count > 0 and voiced == scene_count,
            "visuals": scene_count > 0 and visualized == scene_count,
            "captions": has_captions,
            "render": p.final_video_asset_id is not None,
        },
    )
    return detail


@router.get("", response_model=Page[ProjectSummary])
async def list_projects(
    user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: ProjectStatus | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=200),
    include_archived: bool = False,
) -> Page[ProjectSummary]:
    stmt = select(Project).where(Project.owner_id == user.id)
    if not include_archived:
        stmt = stmt.where(Project.archived_at.is_(None))
    if status_filter:
        stmt = stmt.where(Project.status == status_filter)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Project.title).like(like) | func.lower(Project.topic).like(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(Project.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    items = [await _summary(db, p) for p in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=ProjectStats)
async def project_stats(user: CurrentUser, db: DB) -> ProjectStats:
    rows = (await db.execute(select(Project.status, func.count()).where(Project.owner_id == user.id, Project.archived_at.is_(None)).group_by(Project.status))).all()
    counts = {s.value if hasattr(s, "value") else str(s): int(c) for s, c in rows}
    generating = sum(v for k, v in counts.items() if k in ("researching", "scripting", "storyboarding", "generating", "rendering"))
    return ProjectStats(total=sum(counts.values()), drafts=counts.get("draft", 0) + counts.get("editing", 0), generating=generating, completed=counts.get("completed", 0), failed=counts.get("failed", 0))


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, user: CurrentUser, db: DB) -> ProjectDetail:
    from app.services.billing_service import ensure_subscription

    sub = await ensure_subscription(db, user)
    if body.target_duration_minutes > sub.max_video_minutes:
        raise ValidationError(f"Your plan allows videos up to {sub.max_video_minutes} minutes. Upgrade to create longer videos.")
    if body.resolution == "4k" and sub.max_resolution != "4k":
        raise ValidationError("4K export requires the Pro plan or higher.")
    if body.resolution == "1440p" and sub.max_resolution not in ("1440p", "4k"):
        raise ValidationError("1440p export requires the Pro plan or higher.")
    settings_ = (body.settings or ProjectSettings()).model_dump(mode="json")
    settings_["voice"]["language"] = body.language
    project = Project(owner_id=user.id, **body.model_dump(exclude={"settings"}), settings=settings_, status=ProjectStatus.DRAFT)
    db.add(project)
    await db.flush()
    await db.refresh(project, attribute_names=["research"])
    return await _detail(db, project)


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project: OwnedProject, db: DB) -> ProjectDetail:
    project.last_opened_at = datetime.now(UTC)
    return await _detail(db, project)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(body: ProjectUpdate, project: OwnedProject, db: DB) -> ProjectDetail:
    data = body.model_dump(exclude_unset=True)
    if "settings" in data and data["settings"] is not None:
        merged = {**(project.settings or {})}
        for k, v in data["settings"].items():
            merged[k] = {**merged.get(k, {}), **v} if isinstance(v, dict) and isinstance(merged.get(k), dict) else v
        # validate against the schema (ignore unknown keys)
        ProjectSettings.model_validate(merged)
        project.settings = merged
        data.pop("settings")
    for k, v in data.items():
        setattr(project, k, v)
    if "aspect_ratio" in data or "resolution" in data:
        from app.db.session import get_sync_engine  # noqa: F401  (keeps import surface obvious)
        from app.models.timeline import Timeline
        from app.models.enums import dimensions_for

        tl = (await db.execute(select(Timeline).where(Timeline.project_id == project.id))).scalar_one_or_none()
        if tl:
            w, h = dimensions_for(project.aspect_ratio, project.resolution)
            tl.width, tl.height = w, h
            tl.data = {**(tl.data or {}), "width": w, "height": h}
    await db.flush()
    return await _detail(db, project)


@router.delete("/{project_id}", response_model=Message)
async def delete_project(project: OwnedProject, db: DB, hard: bool = False) -> Message:
    if hard:
        await db.delete(project)
        return Message(message="Project permanently deleted")
    project.archived_at = datetime.now(UTC)
    project.status = ProjectStatus.ARCHIVED
    return Message(message="Project archived")


@router.post("/{project_id}/restore", response_model=ProjectDetail)
async def restore_project(project: OwnedProject, db: DB) -> ProjectDetail:
    project.archived_at = None
    project.status = ProjectStatus.DRAFT if not project.final_video_asset_id else ProjectStatus.COMPLETED
    return await _detail(db, project)


@router.post("/{project_id}/duplicate", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
async def duplicate_project(project: OwnedProject, user: CurrentUser, db: DB) -> ProjectDetail:
    clone = Project(
        owner_id=user.id, title=f"{project.title} (copy)", topic=project.topic, description=project.description, niche=project.niche,
        target_audience=project.target_audience, language=project.language, tone=project.tone, video_format=project.video_format,
        target_duration_minutes=project.target_duration_minutes, aspect_ratio=project.aspect_ratio, resolution=project.resolution,
        visual_style=project.visual_style, settings=dict(project.settings or {}), status=ProjectStatus.DRAFT,
    )
    db.add(clone)
    await db.flush()
    await db.refresh(clone, attribute_names=["research"])
    return await _detail(db, clone)


@router.get("/{project_id}/estimate", response_model=CostEstimate)
async def estimate(project: OwnedProject, user: CurrentUser, db: DB, stages: str | None = None) -> CostEstimate:
    scene_count = (await db.execute(select(func.count()).select_from(Scene).where(Scene.project_id == project.id))).scalar_one()
    if not scene_count:
        scene_count = int(project.target_duration_minutes * 60 / float((project.settings or {}).get("scene_target_seconds") or 9))
    visuals = (project.settings or {}).get("visuals") or {}
    ratio = 1.0 if visuals.get("mode") == "ai_video" else float(visuals.get("ai_video_ratio") or 0) if visuals.get("mode") == "mixed" else 0.0
    breakdown = estimate_pipeline_cost(duration_minutes=project.target_duration_minutes, scene_count=scene_count, ai_video_ratio=ratio, stages=stages.split(",") if stages else None)
    total = sum(breakdown.values())
    return CostEstimate(credits=total, breakdown=breakdown, balance=user.credits_balance, sufficient=user.credits_balance >= total)


@router.post("/{project_id}/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED, summary="Run the full AI pipeline")
@limiter.limit(settings.rate_limit_generation)
async def run_pipeline(request: Request, body: PipelineRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    scene_count = (await db.execute(select(func.count()).select_from(Scene).where(Scene.project_id == project.id))).scalar_one() or int(project.target_duration_minutes * 60 / 9)
    breakdown = estimate_pipeline_cost(duration_minutes=project.target_duration_minutes, scene_count=scene_count, stages=body.stages)
    await assert_can_afford(db, user, sum(breakdown.values()))
    job, created = await create_generation_job(
        db, project_id=project.id, user_id=user.id, job_type=JobType.FULL_PIPELINE,
        params={"stages": body.stages, "skip_existing": body.skip_existing, "render_preview": body.render_preview},
        idempotency_key=body.idempotency_key, timeout_seconds=settings.render_job_timeout_seconds, credits_reserved=sum(breakdown.values()),
    )
    if created:
        project.status = ProjectStatus.RESEARCHING if "research" in body.stages else ProjectStatus.GENERATING
        await db.commit()
        from workers.tasks.generation import run_pipeline as task

        res = task.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.get("/{project_id}/jobs", response_model=list[JobPublic])
async def project_jobs(project: OwnedProject, db: DB, limit: int = Query(20, le=100), active_only: bool = False) -> list[JobPublic]:
    from app.schemas.job import RenderJobPublic

    gstmt = select(GenerationJob).where(GenerationJob.project_id == project.id)
    rstmt = select(RenderJob).where(RenderJob.project_id == project.id)
    if active_only:
        gstmt = gstmt.where(GenerationJob.state.not_in(list(TERMINAL_STATES)))
        rstmt = rstmt.where(RenderJob.state.not_in(list(TERMINAL_STATES)))
    gens = (await db.execute(gstmt.order_by(GenerationJob.created_at.desc()).limit(limit))).scalars().all()
    rends = (await db.execute(rstmt.order_by(RenderJob.created_at.desc()).limit(limit))).scalars().all()
    out: list[JobPublic] = [JobPublic.model_validate(j) for j in gens]
    for r in rends:
        rp = RenderJobPublic.model_validate(r)
        if r.output_asset_id:
            a = await db.get(MediaAsset, r.output_asset_id)
            if a:
                rp.output_url = url_for(a.storage_key, filename=a.filename)
        out.append(rp)
    out.sort(key=lambda j: j.created_at, reverse=True)
    return out[:limit]


__all__ = ["router", "uuid", "Voiceover"]
