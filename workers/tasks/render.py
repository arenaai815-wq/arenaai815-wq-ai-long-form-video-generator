"""FFmpeg render task (queue: render)."""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import JobState, MediaSource, ProjectStatus, UsageKind
from app.models.job import GenerationJob, RenderJob
from app.models.media import AudioAsset, MediaAsset, Voiceover
from app.models.project import Project
from app.models.user import User
from app.services import caption_service
from app.services.billing_service import record_usage_sync
from app.services.job_service import JobContext
from app.services.media_service import default_local_path, save_media_asset_sync
from app.storage import get_storage
from workers.celery_app import celery_app
from workers.rendering.compositor import AssetLocator, Compositor, RenderOptions, generate_thumbnail
from workers.tasks.base import run_job

log = get_logger(__name__)


def _locator(db, work: Path) -> AssetLocator:
    storage = get_storage()
    dl = work / "assets"
    dl.mkdir(parents=True, exist_ok=True)

    def resolve(asset_id: str, kind: str | None) -> Path | None:
        key: str | None = None
        ext = "bin"
        try:
            uid = uuid.UUID(str(asset_id))
        except ValueError:
            return None
        if kind == "voiceover":
            vo = db.get(Voiceover, uid)
            if vo and vo.storage_key:
                key, ext = vo.storage_key, vo.storage_key.rsplit(".", 1)[-1]
        else:
            ma = db.get(MediaAsset, uid)
            if ma:
                key, ext = ma.storage_key, ma.storage_key.rsplit(".", 1)[-1]
            else:
                aa = db.get(AudioAsset, uid)
                if aa:
                    key, ext = aa.storage_key, aa.storage_key.rsplit(".", 1)[-1]
        if not key:
            return None
        local = default_local_path(key)
        if local and local.exists():
            return local
        target = dl / f"{asset_id}.{ext}"
        if not target.exists():
            storage.download_to(key, target)
        return target

    return AssetLocator(resolve=resolve)


@celery_app.task(bind=True, name="workers.tasks.render.run_render_job", max_retries=1, soft_time_limit=settings.render_job_timeout_seconds, time_limit=settings.render_job_timeout_seconds + 120)
def run_render_job(self, job_id: str) -> dict[str, Any]:
    def body(ctx: JobContext) -> dict[str, Any]:
        job: RenderJob = ctx.job  # type: ignore[assignment]
        project = ctx.db.get(Project, job.project_id)
        user = ctx.db.get(User, job.user_id)
        if project is None or user is None:
            raise ValueError("project or user missing")
        doc = job.timeline_snapshot or {}
        if not doc.get("tracks"):
            raise ValueError("Timeline is empty - generate scenes first")

        project.status = ProjectStatus.RENDERING
        ctx.set_state(JobState.RENDERING, "Rendering video... starting", progress=2)
        work = Path(settings.render_work_dir) / str(job.id)
        work.mkdir(parents=True, exist_ok=True)
        started = time.time()

        cap = caption_service.current_caption(ctx.db, project.id)
        cues = cap.cues if (cap and job.burn_captions) else []
        cap_style = dict(cap.style) if cap else {}
        cap_style.update(doc.get("captions") or {})

        wm_cfg = doc.get("watermark") or {}
        wm_text = None
        wm_image = None
        if job.include_watermark:
            wm_text = wm_cfg.get("text") or settings.watermark_text
            if wm_cfg.get("asset_id"):
                wm_image = _locator(ctx.db, work).path(wm_cfg["asset_id"], "image")

        options = RenderOptions(
            width=job.width, height=job.height, fps=job.fps,
            crf=settings.render_crf, preset=settings.render_preset,
            burn_captions=job.burn_captions, watermark_text=wm_text, watermark_image=wm_image,
            watermark_position=wm_cfg.get("position", "bottom_right"), watermark_opacity=float(wm_cfg.get("opacity", 0.6)),
            range_start=(job.params or {}).get("range_start"), range_end=(job.params or {}).get("range_end"),
            is_preview=job.is_preview, threads=settings.render_threads,
        )
        if job.is_preview:
            # Previews render at <=720p for speed
            scale = min(1.0, 720 / max(1, job.height))
            options.width, options.height = int(job.width * scale) // 2 * 2, int(job.height * scale) // 2 * 2

        # If this render was queued by a full pipeline job, mirror progress onto the parent
        # so its SSE stream keeps moving (RENDERING 76% -> 99%) instead of stalling at handoff.
        parent_ctx: JobContext | None = None
        parent_id = (job.params or {}).get("pipeline_job_id")
        if parent_id:
            parent = ctx.db.get(GenerationJob, uuid.UUID(parent_id))
            if parent and parent.state == JobState.RENDERING:
                parent_ctx = JobContext(ctx.db, parent, worker_id=ctx.worker_id)
        parent_base = float(parent_ctx.job.progress) if parent_ctx else 0.0
        last_parent_tick = [0.0]

        def progress(frac: float, msg: str) -> None:
            ctx.stage_progress(JobState.RENDERING, frac, msg, base=2, weight=90)
            if parent_ctx and (frac - last_parent_tick[0] >= 0.02 or frac >= 1.0):
                last_parent_tick[0] = frac
                parent_ctx.progress(parent_base + (99 - parent_base) * frac, f"Rendering video... {int(frac * 100)}%")

        comp = Compositor(doc, locator=_locator(ctx.db, work), options=options, captions=cues, caption_style=cap_style, work_dir=work, progress=progress, check_cancelled=ctx.check_cancelled)
        output = work / ("preview.mp4" if job.is_preview else "final.mp4")
        result = comp.render(output)

        ctx.set_state(JobState.UPLOADING, "Uploading video...", progress=93)
        data = output.read_bytes()
        filename = f"{_slug(project.title)}-{'preview' if job.is_preview else 'final'}-{job.width}x{job.height}.mp4"
        asset = save_media_asset_sync(
            ctx.db, owner_id=user.id, project_id=project.id, data=data, content_type="video/mp4", filename=filename,
            source=MediaSource.RENDER, provider="ffmpeg", width=result["width"], height=result["height"],
            duration_seconds=result["duration"], fps=float(job.fps), tags=["render", "preview" if job.is_preview else "final"],
            category="renders", make_thumb=False,
        )
        thumb = work / "thumb.jpg"
        try:
            generate_thumbnail(output, thumb, at=min(2.0, result["duration"] / 3))
            tkey = asset.storage_key.rsplit(".", 1)[0] + ".thumb.jpg"
            get_storage().put_bytes(tkey, thumb.read_bytes(), "image/jpeg")
            asset.thumbnail_key = tkey
        except Exception as exc:  # thumbnails are best-effort
            ctx.log(f"thumbnail failed: {exc}", level="warning")

        job.output_asset_id = asset.id
        job.output_duration_seconds = result["duration"]
        job.output_size_bytes = len(data)
        job.render_seconds = round(time.time() - started, 1)
        if not job.is_preview:
            project.final_video_asset_id = asset.id
            project.status = ProjectStatus.COMPLETED
            if asset.thumbnail_key and not project.thumbnail_asset_id:
                project.thumbnail_asset_id = asset.id
        else:
            project.status = ProjectStatus.EDITING
        record_usage_sync(ctx.db, user, UsageKind.RENDER_SECONDS, result["duration"], "seconds", project_id=project.id, job_id=job.id, charge=not job.is_preview)
        ctx.db.commit()

        # Notify the parent pipeline job (if any) that everything is done
        parent_id = (job.params or {}).get("pipeline_job_id")
        if parent_id:
            parent = ctx.db.get(GenerationJob, uuid.UUID(parent_id))
            if parent and parent.state == JobState.RENDERING:
                parent_ctx = JobContext(ctx.db, parent, worker_id=ctx.worker_id)
                parent_ctx.complete({**(parent.result or {}), "render_job_id": str(job.id), "output_asset_id": str(asset.id)}, message="Video ready")

        shutil.rmtree(work, ignore_errors=True)
        return {"output_asset_id": str(asset.id), "duration": result["duration"], "size_bytes": len(data), "render_seconds": job.render_seconds}

    try:
        return run_job(self, job_id, body, render=True)
    finally:
        # If the job failed, propagate failure to a waiting pipeline job
        from app.db.session import sync_session

        with sync_session() as db:
            rj = db.get(RenderJob, uuid.UUID(job_id))
            if rj and rj.state in (JobState.FAILED, JobState.CANCELLED):
                parent_id = (rj.params or {}).get("pipeline_job_id")
                if parent_id:
                    parent = db.get(GenerationJob, uuid.UUID(parent_id))
                    if parent and parent.state == JobState.RENDERING:
                        pctx = JobContext(db, parent, worker_id="render")
                        if rj.state == JobState.FAILED:
                            pctx.fail(f"Render failed: {rj.error}")
                        else:
                            pctx.cancelled()
                proj = db.get(Project, rj.project_id)
                if proj and proj.status == ProjectStatus.RENDERING:
                    proj.status = ProjectStatus.FAILED if rj.state == JobState.FAILED else ProjectStatus.EDITING


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9]+", "-", s or "video").strip("-").lower()[:60] or "video"
