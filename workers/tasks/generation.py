"""AI generation tasks (queue: generation)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import JobState, JobType, ProjectStatus, VisualType
from app.models.project import Project
from app.models.script import ScriptSection
from app.models.user import User
from app.services import (
    caption_service,
    research_service,
    scene_service,
    script_service,
    timeline_service,
    visual_service,
    voiceover_service,
)
from app.services.job_service import JobContext, overall_progress
from workers.celery_app import celery_app
from workers.tasks.base import run_job, Handoff

log = get_logger(__name__)


def _load(ctx: JobContext) -> tuple[Project, User]:
    project = ctx.db.get(Project, ctx.job.project_id)
    user = ctx.db.get(User, ctx.job.user_id)
    if project is None or user is None:
        raise ValueError("project or user no longer exists")
    return project, user


def _stage_cb(ctx: JobContext, state: JobState, *, stages: list[JobState] | None = None):
    """Return a progress(fraction, message) callback bound to a pipeline stage."""

    def cb(fraction: float, message: str | None = None) -> None:
        if stages:
            ctx.stage_progress(state, fraction, message, base=overall_progress(state, 0.0, stages), weight=overall_progress(state, 1.0, stages) - overall_progress(state, 0.0, stages))
        else:
            ctx.stage_progress(state, fraction, message)

    return cb


# --------------------------------------------------------------------------- individual stages


def do_research(ctx: JobContext, project: Project, user: User, params: dict[str, Any], stages=None) -> dict[str, Any]:
    cb = _stage_cb(ctx, JobState.RESEARCHING, stages=stages)
    cb(0.02, "Researching topic... starting")
    project.status = ProjectStatus.RESEARCHING
    research = research_service.generate_research_sync(
        ctx.db, project, user,
        section_count=int(params.get("section_count") or 6),
        depth=str(params.get("depth") or "standard"),
        focus=params.get("focus"),
        include_sources=bool(params.get("include_sources", True)),
        job_id=ctx.job.id, progress=cb,
    )
    project.status = ProjectStatus.SCRIPTING
    ctx.db.commit()
    cb(1.0, "Research complete")
    return {"research_id": str(research.id), "sections": len(research.sections)}


def do_script(ctx: JobContext, project: Project, user: User, params: dict[str, Any], stages=None) -> dict[str, Any]:
    cb = _stage_cb(ctx, JobState.GENERATING_SCRIPT, stages=stages)
    cb(0.02, "Generating script... starting")
    project.status = ProjectStatus.SCRIPTING
    script = script_service.generate_script_sync(
        ctx.db, project, user,
        target_duration_minutes=params.get("target_duration_minutes"),
        tone=params.get("tone"),
        words_per_minute=params.get("words_per_minute"),
        instructions=params.get("instructions"),
        job_id=ctx.job.id, progress=cb,
    )
    project.status = ProjectStatus.STORYBOARDING
    ctx.db.commit()
    cb(1.0, f"Script complete: {script.word_count} words")
    return {"script_id": str(script.id), "word_count": script.word_count, "estimated_duration_seconds": script.estimated_duration_seconds}


def do_scenes(ctx: JobContext, project: Project, user: User, params: dict[str, Any], stages=None) -> dict[str, Any]:
    cb = _stage_cb(ctx, JobState.GENERATING_SCENES, stages=stages)
    cb(0.02, "Building storyboard... starting")
    script = script_service.current_script(ctx.db, project.id)
    if script is None:
        raise ValueError("Generate a script before building scenes")
    scenes = scene_service.generate_scenes_sync(ctx.db, project, user, script, scene_target_seconds=params.get("scene_target_seconds"), job_id=ctx.job.id, progress=cb)
    timeline_service.sync_from_scenes(ctx.db, project, scenes)
    project.status = ProjectStatus.STORYBOARDING
    ctx.db.commit()
    cb(1.0, f"Storyboard complete: {len(scenes)} scenes")
    return {"scene_count": len(scenes)}


def do_voiceover(ctx: JobContext, project: Project, user: User, params: dict[str, Any], stages=None) -> dict[str, Any]:
    cb = _stage_cb(ctx, JobState.GENERATING_AUDIO, stages=stages)
    cb(0.02, "Generating voiceover... starting")
    scenes = scene_service.scenes_for_project(ctx.db, project.id)
    ids = params.get("scene_ids")
    if ids:
        wanted = {uuid.UUID(str(i)) for i in ids}
        scenes = [s for s in scenes if s.id in wanted]
    if not scenes:
        raise ValueError("No scenes to voice - build the storyboard first")
    project.status = ProjectStatus.GENERATING
    vos = voiceover_service.generate_voiceovers_sync(
        ctx.db, project, user, scenes,
        force=bool(params.get("force")), voice_id=params.get("voice_id"), provider=params.get("provider"),
        language=params.get("language"), style=params.get("style"), speed=params.get("speed"),
        job_id=ctx.job.id, progress=cb,
    )
    all_scenes = scene_service.scenes_for_project(ctx.db, project.id)
    timeline_service.sync_from_scenes(ctx.db, project, all_scenes)
    ctx.db.commit()
    cb(1.0, f"Voiceover complete: {len(vos)} clips")
    return {"voiceover_count": len(vos), "total_audio_seconds": round(sum(v.duration_seconds or 0 for v in vos), 1)}


def do_visuals(ctx: JobContext, project: Project, user: User, params: dict[str, Any], stages=None) -> dict[str, Any]:
    cb = _stage_cb(ctx, JobState.GENERATING_VISUALS, stages=stages)
    cb(0.02, "Creating visuals... starting")
    scenes = scene_service.scenes_for_project(ctx.db, project.id)
    ids = params.get("scene_ids")
    if ids:
        wanted = {uuid.UUID(str(i)) for i in ids}
        scenes = [s for s in scenes if s.id in wanted]
    if not scenes:
        raise ValueError("No scenes to visualise - build the storyboard first")
    project.status = ProjectStatus.GENERATING
    vt = VisualType(params["visual_type"]) if params.get("visual_type") else None
    assets = visual_service.generate_visuals_sync(ctx.db, project, user, scenes, force=bool(params.get("force")), visual_type=vt, provider=params.get("provider"), job_id=ctx.job.id, progress=cb)
    all_scenes = scene_service.scenes_for_project(ctx.db, project.id)
    timeline_service.sync_from_scenes(ctx.db, project, all_scenes)
    ctx.db.commit()
    cb(1.0, f"Visuals complete: {len(assets)} assets")
    return {"asset_count": len(assets)}


def do_captions(ctx: JobContext, project: Project, user: User, params: dict[str, Any], stages=None) -> dict[str, Any]:
    cb = _stage_cb(ctx, JobState.GENERATING_CAPTIONS, stages=stages)
    cb(0.02, "Generating captions... starting")
    scenes = scene_service.scenes_for_project(ctx.db, project.id)
    if not scenes:
        raise ValueError("No scenes - build the storyboard first")
    vos = voiceover_service.voiceovers_for_scenes(ctx.db, scenes)
    cap = caption_service.generate_captions_sync(ctx.db, project, user, scenes, vos, mode=str(params.get("mode") or "auto"), language=params.get("language"), style=params.get("style"), job_id=ctx.job.id, progress=cb)
    ctx.db.commit()
    cb(1.0, f"Captions complete: {cap.cue_count} cues")
    return {"caption_id": str(cap.id), "cue_count": cap.cue_count}


STAGE_FUNCS = {
    "research": (do_research, JobState.RESEARCHING),
    "script": (do_script, JobState.GENERATING_SCRIPT),
    "scenes": (do_scenes, JobState.GENERATING_SCENES),
    "voiceover": (do_voiceover, JobState.GENERATING_AUDIO),
    "visuals": (do_visuals, JobState.GENERATING_VISUALS),
    "captions": (do_captions, JobState.GENERATING_CAPTIONS),
}


# --------------------------------------------------------------------------- celery tasks


@celery_app.task(bind=True, name="workers.tasks.generation.run_generation_job", max_retries=settings.job_max_retries)
def run_generation_job(self, job_id: str) -> dict[str, Any]:
    """Single-stage generation job. `job.job_type` selects the stage."""

    def body(ctx: JobContext) -> dict[str, Any]:
        project, user = _load(ctx)
        jt = ctx.job.job_type
        params = ctx.job.params or {}
        mapping = {
            JobType.RESEARCH: "research",
            JobType.SCRIPT: "script",
            JobType.SCENES: "scenes",
            JobType.VOICEOVER: "voiceover",
            JobType.VISUALS: "visuals",
            JobType.CAPTIONS: "captions",
        }
        if jt == JobType.SCRIPT_SECTION:
            return _regenerate_section(ctx, project, user, params)
        stage = mapping.get(jt)
        if not stage:
            raise ValueError(f"unsupported job type {jt}")
        fn, _ = STAGE_FUNCS[stage]
        result = fn(ctx, project, user, params)
        project.status = _status_after(stage, project)
        ctx.db.commit()
        return result

    return run_job(self, job_id, body)


def _regenerate_section(ctx: JobContext, project: Project, user: User, params: dict[str, Any]) -> dict[str, Any]:
    ctx.set_state(JobState.GENERATING_SCRIPT, "Regenerating section...", progress=10)
    section = ctx.db.get(ScriptSection, ctx.job.target_id)
    if section is None:
        raise ValueError("section not found")
    section = script_service.regenerate_section_sync(ctx.db, project, user, section, instructions=params.get("instructions"), target_words=params.get("target_words"), tone=params.get("tone"), job_id=ctx.job.id)
    ctx.db.commit()
    return {"section_id": str(section.id), "word_count": section.word_count}


def _status_after(stage: str, project: Project) -> ProjectStatus:
    return {
        "research": ProjectStatus.SCRIPTING,
        "script": ProjectStatus.STORYBOARDING,
        "scenes": ProjectStatus.STORYBOARDING,
        "voiceover": ProjectStatus.EDITING,
        "visuals": ProjectStatus.EDITING,
        "captions": ProjectStatus.EDITING,
    }.get(stage, project.status)


@celery_app.task(bind=True, name="workers.tasks.generation.run_pipeline", max_retries=1)
def run_pipeline(self, job_id: str) -> dict[str, Any]:
    """Full topic -> MP4 pipeline in one job with weighted, resumable stages."""

    def body(ctx: JobContext) -> dict[str, Any]:
        project, user = _load(ctx)
        params = ctx.job.params or {}
        wanted = [s for s in params.get("stages") or list(STAGE_FUNCS) + ["render"] if s in STAGE_FUNCS or s == "render"]
        skip_existing = bool(params.get("skip_existing", True))
        completed = set((ctx.job.result or {}).get("completed_stages") or [])  # resume after retry
        stage_states = [STAGE_FUNCS[s][1] for s in wanted if s in STAGE_FUNCS] + ([JobState.RENDERING] if "render" in wanted else [])
        results: dict[str, Any] = dict(ctx.job.result or {})

        for stage in wanted:
            if stage == "render":
                continue
            if stage in completed:
                continue
            if skip_existing and _stage_already_done(ctx, project, stage):
                ctx.log(f"skipping {stage}: already present")
                completed.add(stage)
                continue
            fn, _ = STAGE_FUNCS[stage]
            results[stage] = fn(ctx, project, user, params.get(stage) or {}, stages=stage_states)
            completed.add(stage)
            ctx.job.result = {**results, "completed_stages": sorted(completed)}
            ctx.db.commit()

        if "render" in wanted:
            # Hand off to the dedicated render queue and link the render job to this pipeline
            from app.models.enums import dimensions_for
            from app.models.job import RenderJob
            from app.services.billing_service import ensure_subscription_sync

            sub = ensure_subscription_sync(ctx.db, user)
            tl = timeline_service.get_or_create_timeline(ctx.db, project)
            w, h = dimensions_for(project.aspect_ratio, project.resolution)
            rj = RenderJob(
                project_id=project.id, user_id=user.id, width=w, height=h, fps=30,
                is_preview=bool(params.get("render_preview")), burn_captions=bool(((project.settings or {}).get("captions") or {}).get("burn_in", True)),
                include_watermark=bool(sub.watermark_required or ((project.settings or {}).get("watermark") or {}).get("enabled")),
                timeline_version=tl.version, timeline_snapshot=tl.data, params={"pipeline_job_id": str(ctx.job.id)},
                timeout_seconds=settings.render_job_timeout_seconds, max_attempts=2, stage="Queued", message="Waiting for a render worker...",
            )
            ctx.db.add(rj)
            project.status = ProjectStatus.RENDERING
            ctx.db.commit()
            from workers.tasks.render import run_render_job

            results["render_job_id"] = str(rj.id)
            results["completed_stages"] = sorted(completed)
            ctx.set_state(JobState.RENDERING, "Handed off to render worker", progress=int(overall_progress(JobState.RENDERING, 0.0, stage_states)))
            run_render_job.apply_async(args=[str(rj.id)], queue="render")
            # The render worker completes (or fails) this pipeline job when the MP4 is ready.
            raise Handoff(results)
        project.status = ProjectStatus.EDITING
        ctx.db.commit()
        results["completed_stages"] = sorted(completed)
        return results

    return run_job(self, job_id, body)


def _stage_already_done(ctx: JobContext, project: Project, stage: str) -> bool:
    db = ctx.db
    if stage == "research":
        return project.research is not None and bool(project.research.sections)
    if stage == "script":
        s = script_service.current_script(db, project.id)
        return s is not None and s.word_count > 0
    scenes = scene_service.scenes_for_project(db, project.id)
    if stage == "scenes":
        return len(scenes) > 0
    if stage == "voiceover":
        return bool(scenes) and all(s.voiceover_id for s in scenes)
    if stage == "visuals":
        return bool(scenes) and all(s.visual_asset_id for s in scenes)
    if stage == "captions":
        return caption_service.current_caption(db, project.id) is not None
    return False


@celery_app.task(name="workers.tasks.generation.ping")
def ping() -> str:
    return "pong"


__all__ = ["run_generation_job", "run_pipeline", "ping", "select"]
