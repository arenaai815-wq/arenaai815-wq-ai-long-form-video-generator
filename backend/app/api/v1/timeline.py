from __future__ import annotations

import copy
import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, OwnedProject
from app.core.exceptions import ConflictError, ValidationError
from app.models.media import AudioAsset, MediaAsset, Voiceover
from app.models.scene import Scene
from app.models.timeline import Timeline
from app.schemas.timeline import TimelineDocument, TimelineOpsRequest, TimelinePublic, TimelineSaveRequest
from app.services.media_service import url_for
from app.services.timeline_service import apply_operation, get_or_create_timeline, save_document, sync_from_scenes

router = APIRouter()


async def _with_urls(db: DB, tl: Timeline) -> TimelinePublic:
    """Attach signed src URLs to clips so the browser preview can play them."""
    data = copy.deepcopy(tl.data or {})  # never mutate the ORM-held document
    media_ids, vo_ids = set(), set()
    for tr in data.get("tracks", []):
        for c in tr.get("clips", []):
            if not c.get("asset_id"):
                continue
            (vo_ids if c.get("asset_kind") == "voiceover" else media_ids).add(c["asset_id"])
    urls: dict[str, str | None] = {}
    if media_ids:
        ids = [uuid.UUID(i) for i in media_ids]
        for a in (await db.execute(select(MediaAsset).where(MediaAsset.id.in_(ids)))).scalars():
            urls[str(a.id)] = url_for(a.storage_key)
        for a in (await db.execute(select(AudioAsset).where(AudioAsset.id.in_(ids)))).scalars():
            urls[str(a.id)] = url_for(a.storage_key)
    if vo_ids:
        for v in (await db.execute(select(Voiceover).where(Voiceover.id.in_([uuid.UUID(i) for i in vo_ids])))).scalars():
            urls[str(v.id)] = url_for(v.storage_key)
    for tr in data.get("tracks", []):
        for c in tr.get("clips", []):
            if c.get("asset_id"):
                c["src_url"] = urls.get(c["asset_id"])
    p = TimelinePublic.model_validate(tl)
    p.data = data
    return p


@router.get("", response_model=TimelinePublic)
async def get_timeline(project: OwnedProject, db: DB) -> TimelinePublic:
    tl = await db.run_sync(lambda s: get_or_create_timeline(s, project))
    if not (tl.data or {}).get("tracks") or not any(t.get("clips") for t in tl.data.get("tracks", [])):
        scenes = list((await db.execute(select(Scene).where(Scene.project_id == project.id).order_by(Scene.order_index))).scalars().all())
        if scenes:
            tl = await db.run_sync(lambda s: sync_from_scenes(s, project, scenes))
    return await _with_urls(db, tl)


@router.put("", response_model=TimelinePublic, summary="Save the full timeline document (browser editor)")
async def save_timeline(body: TimelineSaveRequest, project: OwnedProject, db: DB) -> TimelinePublic:
    tl = await db.run_sync(lambda s: get_or_create_timeline(s, project))
    if body.base_version is not None and body.base_version != tl.version:
        raise ConflictError("Timeline was modified elsewhere. Reload and try again.", details={"server_version": tl.version})
    tl = await db.run_sync(lambda s: save_document(s, tl, body.data))
    project.estimated_duration_seconds = tl.duration_seconds
    return await _with_urls(db, tl)


@router.post("/ops", response_model=TimelinePublic, summary="Apply a single edit operation server-side")
async def timeline_op(body: TimelineOpsRequest, project: OwnedProject, db: DB) -> TimelinePublic:
    tl = await db.run_sync(lambda s: get_or_create_timeline(s, project))
    try:
        new_doc = apply_operation(copy.deepcopy(tl.data or {}), body.op, body.payload)
    except (ValueError, KeyError) as exc:
        raise ValidationError(str(exc)) from exc
    tl = await db.run_sync(lambda s: save_document(s, tl, TimelineDocument.model_validate(new_doc)))
    project.estimated_duration_seconds = tl.duration_seconds
    return await _with_urls(db, tl)


@router.post("/sync", response_model=TimelinePublic, summary="Rebuild scene-derived tracks from the storyboard")
async def resync(project: OwnedProject, db: DB, preserve_edits: bool = True) -> TimelinePublic:
    scenes = list((await db.execute(select(Scene).where(Scene.project_id == project.id).order_by(Scene.order_index))).scalars().all())
    tl = await db.run_sync(lambda s: sync_from_scenes(s, project, scenes, preserve_user_edits=preserve_edits))
    return await _with_urls(db, tl)
