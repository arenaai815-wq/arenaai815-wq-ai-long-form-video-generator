from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import JobType, MediaSource, ProjectStatus, UsageKind, VisualType
from app.models.media import MediaAsset, Voiceover
from app.models.scene import Scene
from app.schemas.common import Message
from app.schemas.job import JobPublic
from app.schemas.scene import (
    SceneCreate,
    ScenePublic,
    SceneReorder,
    ScenesGenerateRequest,
    SceneSplitRequest,
    SceneUpdate,
    SceneVisualFromAsset,
    SceneVisualFromStock,
    VisualGenerateRequest,
)
from app.services.billing_service import assert_can_afford, credits_for_usage
from app.services.job_service import create_generation_job
from app.services.media_service import url_for
from app.utils.text import estimate_duration_seconds

router = APIRouter()


async def _scenes(db: DB, project_id: uuid.UUID) -> list[Scene]:
    return list((await db.execute(select(Scene).where(Scene.project_id == project_id).order_by(Scene.order_index))).scalars().all())


async def _decorate(db: DB, scenes: list[Scene]) -> list[ScenePublic]:
    asset_ids = [s.visual_asset_id for s in scenes if s.visual_asset_id]
    vo_ids = [s.voiceover_id for s in scenes if s.voiceover_id]
    assets = {a.id: a for a in (await db.execute(select(MediaAsset).where(MediaAsset.id.in_(asset_ids)))).scalars()} if asset_ids else {}
    vos = {v.id: v for v in (await db.execute(select(Voiceover).where(Voiceover.id.in_(vo_ids)))).scalars()} if vo_ids else {}
    out = []
    t = 0.0
    for s in scenes:
        p = ScenePublic.model_validate(s)
        p.start_time = round(t, 3)
        a = assets.get(s.visual_asset_id) if s.visual_asset_id else None
        if a:
            p.visual_url = url_for(a.storage_key)
            p.visual_thumbnail_url = url_for(a.thumbnail_key or a.storage_key)
            p.visual_kind = a.kind.value
        v = vos.get(s.voiceover_id) if s.voiceover_id else None
        if v:
            p.voiceover_url = url_for(v.storage_key)
            p.voiceover_duration = v.duration_seconds
            p.voiceover_status = v.status
        out.append(p)
        t += float(s.duration_seconds or 0)
    return out


async def _sync_timeline(db: DB, project) -> None:
    """Rebuild timeline from scenes using the sync service inside the async session's connection."""
    from app.services.timeline_service import sync_from_scenes

    scenes = await _scenes(db, project.id)
    # run_sync gives us a sync Session bound to the same transaction
    await db.run_sync(lambda sync_sess: sync_from_scenes(sync_sess, project, scenes))


@router.get("", response_model=list[ScenePublic])
async def list_scenes(project: OwnedProject, db: DB) -> list[ScenePublic]:
    return await _decorate(db, await _scenes(db, project.id))


@router.post("/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED, summary="Break the script into scenes")
@limiter.limit(settings.rate_limit_generation)
async def generate_scenes(request: Request, body: ScenesGenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.SCENES, params=body.model_dump(exclude_none=True))
    if created:
        project.status = ProjectStatus.STORYBOARDING
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.post("/visuals/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED, summary="Generate AI visuals for scenes")
@limiter.limit(settings.rate_limit_generation)
async def generate_visuals(request: Request, body: VisualGenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    scenes = await _scenes(db, project.id)
    if not scenes:
        raise ValidationError("Build the storyboard first")
    targets = [s for s in scenes if (not body.scene_ids or s.id in set(body.scene_ids)) and (body.force or not s.visual_asset_id)]
    n_video = sum(1 for s in targets if (body.visual_type or s.visual_type) == VisualType.AI_VIDEO)
    cost = credits_for_usage(UsageKind.IMAGE_GENERATION, len(targets) - n_video) + (credits_for_usage(UsageKind.VIDEO_GENERATION, n_video) if n_video else 0)
    await assert_can_afford(db, user, cost)
    params = body.model_dump(exclude_none=True, mode="json")
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.VISUALS, params=params, target_id=body.scene_ids[0] if body.scene_ids and len(body.scene_ids) == 1 else None, credits_reserved=cost)
    if created:
        project.status = ProjectStatus.GENERATING
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.post("", response_model=list[ScenePublic], status_code=status.HTTP_201_CREATED)
async def create_scene(body: SceneCreate, project: OwnedProject, db: DB) -> list[ScenePublic]:
    scenes = await _scenes(db, project.id)
    at = len(scenes)
    if body.after_scene_id:
        for i, s in enumerate(scenes):
            if s.id == body.after_scene_id:
                at = i + 1
    new = Scene(project_id=project.id, order_index=at, title=body.title or f"Scene {at + 1}", narration=body.narration, visual_type=body.visual_type, image_prompt=body.image_prompt, duration_seconds=max(body.duration_seconds, estimate_duration_seconds(body.narration)) if body.narration else body.duration_seconds, status="draft")
    scenes.insert(at, new)
    for i, s in enumerate(scenes):
        s.order_index = i
    db.add(new)
    await db.flush()
    await _sync_timeline(db, project)
    return await _decorate(db, await _scenes(db, project.id))


@router.post("/reorder", response_model=list[ScenePublic])
async def reorder(body: SceneReorder, project: OwnedProject, db: DB) -> list[ScenePublic]:
    scenes = await _scenes(db, project.id)
    by_id = {s.id: s for s in scenes}
    if set(body.scene_ids) != set(by_id):
        raise ValidationError("scene_ids must include every scene exactly once")
    for i, sid in enumerate(body.scene_ids):
        by_id[sid].order_index = i
    await db.flush()
    await _sync_timeline(db, project)
    return await _decorate(db, await _scenes(db, project.id))


@router.get("/{scene_id}", response_model=ScenePublic)
async def get_scene(scene_id: uuid.UUID, project: OwnedProject, db: DB) -> ScenePublic:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    return (await _decorate(db, [s]))[0]


@router.patch("/{scene_id}", response_model=ScenePublic)
async def update_scene(scene_id: uuid.UUID, body: SceneUpdate, project: OwnedProject, db: DB) -> ScenePublic:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    data = body.model_dump(exclude_unset=True)
    if "visual_asset_id" in data and data["visual_asset_id"]:
        a = await db.get(MediaAsset, data["visual_asset_id"])
        if a is None or a.owner_id != project.owner_id:
            raise NotFoundError("Asset not found")
    narration_changed = "narration" in data and data["narration"] != s.narration
    for k, v in data.items():
        setattr(s, k, v)
    if narration_changed:
        # Narration edits invalidate the previous voiceover for this scene
        s.voiceover_id = None
        s.status = "visualized" if s.visual_asset_id else "draft"
        if "duration_seconds" not in data:
            s.duration_seconds = max(2.0, estimate_duration_seconds(s.narration))
    await db.flush()
    await _sync_timeline(db, project)
    return (await _decorate(db, [s]))[0]


@router.delete("/{scene_id}", response_model=list[ScenePublic])
async def delete_scene(scene_id: uuid.UUID, project: OwnedProject, db: DB) -> list[ScenePublic]:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    await db.delete(s)
    await db.flush()
    scenes = await _scenes(db, project.id)
    for i, x in enumerate(scenes):
        x.order_index = i
    await db.flush()
    await _sync_timeline(db, project)
    return await _decorate(db, scenes)


@router.post("/{scene_id}/split", response_model=list[ScenePublic])
async def split_scene(scene_id: uuid.UUID, body: SceneSplitRequest, project: OwnedProject, db: DB) -> list[ScenePublic]:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    text = s.narration
    at = min(max(1, body.at_character), len(text) - 1)
    # snap to nearest whitespace
    while at < len(text) and not text[at].isspace():
        at += 1
    left, right = text[:at].strip(), text[at:].strip()
    if not left or not right:
        raise ValidationError("Split point must leave text on both sides")
    scenes = await _scenes(db, project.id)
    s.narration = left
    s.duration_seconds = max(2.0, estimate_duration_seconds(left))
    s.voiceover_id = None
    new = Scene(project_id=project.id, section_id=s.section_id, order_index=s.order_index + 1, title=f"{s.title or 'Scene'} (b)", narration=right, visual_description=s.visual_description, image_prompt=s.image_prompt, video_prompt=s.video_prompt, negative_prompt=s.negative_prompt, visual_type=s.visual_type, duration_seconds=max(2.0, estimate_duration_seconds(right)), transition=s.transition, transition_duration=s.transition_duration, motion_effect=s.motion_effect, music_mood=s.music_mood, keywords=list(s.keywords or []), status="draft")
    db.add(new)
    for x in scenes:
        if x.order_index > s.order_index:
            x.order_index += 1
    await db.flush()
    await _sync_timeline(db, project)
    return await _decorate(db, await _scenes(db, project.id))


@router.post("/{scene_id}/visual/from-asset", response_model=ScenePublic, summary="Use an existing media asset as the scene visual")
async def visual_from_asset(scene_id: uuid.UUID, body: SceneVisualFromAsset, project: OwnedProject, db: DB) -> ScenePublic:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    a = await db.get(MediaAsset, body.asset_id)
    if a is None or a.owner_id != project.owner_id:
        raise NotFoundError("Asset not found")
    s.visual_asset_id = a.id
    s.visual_type = VisualType.UPLOAD if a.source == MediaSource.UPLOAD else VisualType.STOCK_VIDEO if a.source == MediaSource.STOCK and a.kind.value == "video" else VisualType.STOCK_IMAGE if a.source == MediaSource.STOCK else VisualType.AI_VIDEO if a.kind.value == "video" else VisualType.AI_IMAGE
    s.status = "ready" if s.voiceover_id else "visualized"
    await db.flush()
    await _sync_timeline(db, project)
    return (await _decorate(db, [s]))[0]


@router.post("/{scene_id}/visual/from-stock", response_model=ScenePublic, summary="Import a stock item and assign it to the scene")
async def visual_from_stock(scene_id: uuid.UUID, body: SceneVisualFromStock, project: OwnedProject, user: CurrentUser, db: DB) -> ScenePublic:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    from app.providers import get_registry
    from app.providers.base import StockMediaItem
    from app.services.media_service import save_media_asset_sync

    item = StockMediaItem(id=body.item_id, kind=body.kind, url=body.download_url, download_url=body.download_url, thumbnail_url=None, width=body.width, height=body.height, duration_seconds=body.duration_seconds, author=None, source=body.source)
    import anyio

    provider = get_registry().stock(body.source if body.source != "mock" else None)
    data, ctype = await anyio.to_thread.run_sync(provider.download, item)
    asset = await db.run_sync(
        lambda ss: save_media_asset_sync(ss, owner_id=user.id, project_id=project.id, scene_id=s.id, data=data, content_type=ctype, filename=f"stock-{body.source}-{body.item_id}.{ 'mp4' if body.kind == 'video' else 'jpg'}", source=MediaSource.STOCK, provider=body.source, provider_ref=body.item_id, width=body.width, height=body.height, duration_seconds=body.duration_seconds, category="stock", is_reusable=True)
    )
    s.visual_asset_id = asset.id
    s.visual_type = VisualType.STOCK_VIDEO if body.kind == "video" else VisualType.STOCK_IMAGE
    s.status = "ready" if s.voiceover_id else "visualized"
    await db.flush()
    await _sync_timeline(db, project)
    return (await _decorate(db, [s]))[0]


@router.delete("/{scene_id}/visual", response_model=Message)
async def clear_visual(scene_id: uuid.UUID, project: OwnedProject, db: DB) -> Message:
    s = await db.get(Scene, scene_id)
    if s is None or s.project_id != project.id:
        raise NotFoundError("Scene not found")
    s.visual_asset_id = None
    s.status = "voiced" if s.voiceover_id else "draft"
    await db.flush()
    await _sync_timeline(db, project)
    return Message(message="Visual removed from scene")
