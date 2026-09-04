"""Per-scene visual generation (AI image / AI video / stock) via the provider layer."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import MediaSource, UsageKind, VisualType, dimensions_for
from app.models.media import MediaAsset
from app.models.project import Project
from app.models.scene import Scene
from app.models.user import User
from app.providers import get_registry
from app.services.billing_service import record_usage_sync
from app.services.media_service import save_media_asset_sync

log = get_logger(__name__)
MAX_PARALLEL_VISUALS = 3


def style_suffix(project: Project) -> str:
    return f"{project.visual_style}, consistent colour grade, no text, no watermark"


def image_dimensions(project: Project) -> tuple[int, int]:
    w, h = dimensions_for(project.aspect_ratio, project.resolution)
    # Generation happens at <=1080p; the compositor upscales/crops to the export size
    scale = min(1.0, 1920 / max(w, h))
    return int(w * scale) // 2 * 2, int(h * scale) // 2 * 2


def video_dimensions_for(project: Project) -> tuple[int, int]:
    w, h = dimensions_for(project.aspect_ratio, "720p")
    return w, h


def generate_visual_for_scene(
    db: Session,
    project: Project,
    user: User,
    scene: Scene,
    *,
    visual_type: VisualType | None = None,
    provider: str | None = None,
    prompt_override: str | None = None,
    job_id=None,
) -> MediaAsset:
    reg = get_registry()
    vtype = visual_type or scene.visual_type
    visuals_cfg = (project.settings or {}).get("visuals") or {}

    if vtype == VisualType.AI_VIDEO:
        vp = reg.video(provider or visuals_cfg.get("video_provider"))
        w, h = video_dimensions_for(project)
        prompt = prompt_override or scene.video_prompt or scene.image_prompt or scene.visual_description or scene.narration[:200]
        res = vp.generate_video(
            f"{prompt}, {style_suffix(project)}",
            width=w,
            height=h,
            duration_seconds=min(10.0, max(3.0, float(scene.duration_seconds or 6))),
            style=project.visual_style,
        )
        asset = save_media_asset_sync(
            db,
            owner_id=user.id,
            project_id=project.id,
            scene_id=scene.id,
            data=res.data,
            content_type=res.content_type,
            filename=f"scene-{scene.order_index + 1:03d}-ai-video.mp4",
            source=MediaSource.AI_VIDEO,
            prompt=prompt,
            provider=res.usage.provider,
            provider_ref=res.provider_ref,
            width=res.width,
            height=res.height,
            duration_seconds=res.duration_seconds,
            fps=res.fps,
            tags=list(scene.keywords or []),
            category="ai-video",
        )
        record_usage_sync(db, user, UsageKind.VIDEO_GENERATION, 1, "clips", metrics=res.usage, project_id=project.id, job_id=job_id)
    elif vtype in (VisualType.STOCK_VIDEO, VisualType.STOCK_IMAGE):
        sp = reg.stock()
        kind = "video" if vtype == VisualType.STOCK_VIDEO else "image"
        query = " ".join(scene.keywords[:3]) if scene.keywords else (scene.suggested_footage or scene.title or project.topic)[:80]
        orientation = "landscape" if project.aspect_ratio in ("16:9", "4:3") else "portrait" if project.aspect_ratio == "9:16" else "square"
        items = sp.search(query, kind=kind, orientation=orientation, per_page=5, min_duration=scene.duration_seconds if kind == "video" else None)
        if not items:
            items = sp.search(project.topic[:60], kind=kind, orientation=orientation, per_page=5)
        if not items:
            # graceful fallback to AI image
            return generate_visual_for_scene(db, project, user, scene, visual_type=VisualType.AI_IMAGE, provider=provider, prompt_override=prompt_override, job_id=job_id)
        item = items[0]
        data, ctype = sp.download(item)
        asset = save_media_asset_sync(
            db,
            owner_id=user.id,
            project_id=project.id,
            scene_id=scene.id,
            data=data,
            content_type=ctype,
            filename=f"scene-{scene.order_index + 1:03d}-stock-{item.source}-{item.id}.{ 'mp4' if kind == 'video' else 'jpg'}",
            source=MediaSource.STOCK,
            prompt=query,
            provider=item.source,
            provider_ref=item.id,
            width=item.width,
            height=item.height,
            duration_seconds=item.duration_seconds,
            tags=list(scene.keywords or []) + [f"license:{item.license}", f"author:{item.author or 'unknown'}"],
            category="stock",
        )
    else:
        ip = reg.image(provider or visuals_cfg.get("image_provider"))
        w, h = image_dimensions(project)
        prompt = prompt_override or scene.image_prompt or scene.visual_description or scene.narration[:200]
        res = ip.generate_image(
            f"{prompt}, {style_suffix(project)}",
            width=w,
            height=h,
            style=project.visual_style,
            negative_prompt=scene.negative_prompt,
        )
        asset = save_media_asset_sync(
            db,
            owner_id=user.id,
            project_id=project.id,
            scene_id=scene.id,
            data=res.data,
            content_type=res.content_type,
            filename=f"scene-{scene.order_index + 1:03d}-ai-image.{ 'png' if 'png' in res.content_type else 'jpg'}",
            source=MediaSource.AI_IMAGE,
            prompt=res.revised_prompt or prompt,
            provider=res.usage.provider,
            provider_ref=res.provider_ref,
            width=res.width,
            height=res.height,
            tags=list(scene.keywords or []),
            category="ai-images",
        )
        record_usage_sync(db, user, UsageKind.IMAGE_GENERATION, 1, "images", metrics=res.usage, project_id=project.id, job_id=job_id)

    scene.visual_asset_id = asset.id
    scene.visual_type = vtype
    scene.status = "ready" if scene.voiceover_id else "visualized"
    if project.thumbnail_asset_id is None and asset.kind.value == "image":
        project.thumbnail_asset_id = asset.id
    db.flush()
    return asset


def generate_visuals_sync(
    db: Session,
    project: Project,
    user: User,
    scenes: list[Scene],
    *,
    force: bool = False,
    visual_type: VisualType | None = None,
    provider: str | None = None,
    job_id=None,
    progress: Callable[[float, str], None] | None = None,
) -> list[MediaAsset]:
    todo = [s for s in scenes if force or not s.visual_asset_id]
    total = len(todo) or 1
    done = 0
    results: list[MediaAsset] = []
    failures: list[str] = []

    # Provider calls run in parallel; DB writes are serialised on the main thread.
    from app.providers.base import ImageResult  # noqa: F401  (typing only)

    def work(scene: Scene):
        # Each worker thread needs its own session-free path: we call providers only, then persist on main thread.
        try:
            return scene, _generate_bytes(project, scene, visual_type, provider), None
        except Exception as exc:
            return scene, None, exc

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_VISUALS) as pool:
        for scene, payload, err in pool.map(work, todo):
            done += 1
            if err is not None or payload is None:
                failures.append(f"scene {scene.order_index + 1}: {err}")
                log.warning("visual failed", scene_id=str(scene.id), error=str(err))
                continue
            asset = _persist(db, project, user, scene, payload, job_id)
            results.append(asset)
            if progress:
                progress(done / total, f"Creating visuals... {done}/{total} scenes")
            db.commit()
    if failures and todo and len(failures) == len(todo):
        raise RuntimeError("Visual generation failed for every scene: " + "; ".join(failures[:3]))
    return results


def _generate_bytes(project: Project, scene: Scene, visual_type: VisualType | None, provider: str | None) -> dict:
    """Provider-only part of generation (thread-safe: no DB access)."""
    reg = get_registry()
    vtype = visual_type or scene.visual_type
    visuals_cfg = (project.settings or {}).get("visuals") or {}
    if vtype == VisualType.AI_VIDEO:
        vp = reg.video(provider or visuals_cfg.get("video_provider"))
        w, h = video_dimensions_for(project)
        prompt = scene.video_prompt or scene.image_prompt or scene.visual_description or scene.narration[:200]
        res = vp.generate_video(f"{prompt}, {style_suffix(project)}", width=w, height=h, duration_seconds=min(10.0, max(3.0, float(scene.duration_seconds or 6))), style=project.visual_style)
        return {"vtype": vtype, "data": res.data, "content_type": res.content_type, "prompt": prompt, "provider": res.usage.provider, "ref": res.provider_ref, "width": res.width, "height": res.height, "duration": res.duration_seconds, "fps": res.fps, "usage": res.usage, "usage_kind": UsageKind.VIDEO_GENERATION, "source": MediaSource.AI_VIDEO, "category": "ai-video", "ext": "mp4"}
    if vtype in (VisualType.STOCK_VIDEO, VisualType.STOCK_IMAGE):
        sp = reg.stock()
        kind = "video" if vtype == VisualType.STOCK_VIDEO else "image"
        query = " ".join(scene.keywords[:3]) if scene.keywords else (scene.suggested_footage or scene.title or project.topic)[:80]
        orientation = "landscape" if project.aspect_ratio in ("16:9", "4:3") else "portrait" if project.aspect_ratio == "9:16" else "square"
        items = sp.search(query, kind=kind, orientation=orientation, per_page=5) or sp.search(project.topic[:60], kind=kind, orientation=orientation, per_page=5)
        if items:
            item = items[0]
            data, ctype = sp.download(item)
            return {"vtype": vtype, "data": data, "content_type": ctype, "prompt": query, "provider": item.source, "ref": item.id, "width": item.width, "height": item.height, "duration": item.duration_seconds, "fps": None, "usage": None, "usage_kind": None, "source": MediaSource.STOCK, "category": "stock", "ext": "mp4" if kind == "video" else "jpg", "tags": [f"license:{item.license}", f"author:{item.author or 'unknown'}"]}
        vtype = VisualType.AI_IMAGE  # fall through
    ip = reg.image(provider or visuals_cfg.get("image_provider"))
    w, h = image_dimensions(project)
    prompt = scene.image_prompt or scene.visual_description or scene.narration[:200]
    res = ip.generate_image(f"{prompt}, {style_suffix(project)}", width=w, height=h, style=project.visual_style, negative_prompt=scene.negative_prompt)
    return {"vtype": VisualType.AI_IMAGE, "data": res.data, "content_type": res.content_type, "prompt": res.revised_prompt or prompt, "provider": res.usage.provider, "ref": res.provider_ref, "width": res.width, "height": res.height, "duration": None, "fps": None, "usage": res.usage, "usage_kind": UsageKind.IMAGE_GENERATION, "source": MediaSource.AI_IMAGE, "category": "ai-images", "ext": "png" if "png" in res.content_type else "jpg"}


def _persist(db: Session, project: Project, user: User, scene: Scene, p: dict, job_id) -> MediaAsset:
    asset = save_media_asset_sync(
        db,
        owner_id=user.id,
        project_id=project.id,
        scene_id=scene.id,
        data=p["data"],
        content_type=p["content_type"],
        filename=f"scene-{scene.order_index + 1:03d}-{p['category']}.{p['ext']}",
        source=p["source"],
        prompt=p["prompt"],
        provider=p["provider"],
        provider_ref=p["ref"],
        width=p["width"],
        height=p["height"],
        duration_seconds=p["duration"],
        fps=p["fps"],
        tags=list(scene.keywords or []) + list(p.get("tags") or []),
        category=p["category"],
    )
    if p["usage_kind"]:
        record_usage_sync(db, user, p["usage_kind"], 1, "items", metrics=p["usage"], project_id=project.id, job_id=job_id)
    scene.visual_asset_id = asset.id
    scene.visual_type = p["vtype"]
    scene.status = "ready" if scene.voiceover_id else "visualized"
    if project.thumbnail_asset_id is None and asset.kind.value == "image":
        project.thumbnail_asset_id = asset.id
    db.flush()
    return asset
