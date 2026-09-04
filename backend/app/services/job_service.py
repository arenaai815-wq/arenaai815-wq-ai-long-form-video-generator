"""Job lifecycle management shared by the API (async) and workers (sync).

Design notes
------------
* Every job row is created **before** the Celery task is enqueued and the task carries the
  job id. Workers load the row, check `cancel_requested`, and update `state/progress`.
* `idempotency_key` (unique per user) means retried HTTP requests or duplicate clicks
  return the same job instead of scheduling twice.
* Progress is persisted to Postgres *and* published to Redis so SSE clients update live
  and late joiners can still read the latest state.
* `JobContext` is the tiny API workers use: `ctx.progress(...)`, `ctx.check_cancelled()`,
  `ctx.log(...)`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.enums import STAGE_WEIGHTS, TERMINAL_STATES, JobState, JobType
from app.models.job import GenerationJob, RenderJob
from app.realtime.events import (
    build_event,
    is_cancel_requested,
    publish_event,
    publish_event_async,
    request_cancel_async,
)

log = get_logger(__name__)

STAGE_LABELS: dict[JobState, str] = {
    JobState.QUEUED: "Queued",
    JobState.PROCESSING: "Preparing",
    JobState.RESEARCHING: "Researching topic",
    JobState.GENERATING_SCRIPT: "Generating script",
    JobState.GENERATING_SCENES: "Building storyboard",
    JobState.GENERATING_AUDIO: "Generating voiceover",
    JobState.GENERATING_VISUALS: "Creating visuals",
    JobState.GENERATING_CAPTIONS: "Generating captions",
    JobState.RENDERING: "Rendering video",
    JobState.UPLOADING: "Uploading",
    JobState.COMPLETED: "Complete",
    JobState.FAILED: "Failed",
    JobState.CANCELLED: "Cancelled",
}


class JobCancelled(Exception):
    """Raised inside a worker when cancellation was requested."""


def _now() -> datetime:
    return datetime.now(UTC)


def _serialize_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in result.items()}


# --------------------------------------------------------------------------- async (API)


async def create_generation_job(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    job_type: JobType,
    params: dict[str, Any] | None = None,
    target_id: uuid.UUID | None = None,
    parent_job_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    timeout_seconds: int | None = None,
    credits_reserved: int = 0,
) -> tuple[GenerationJob, bool]:
    """Return (job, created). If an active job with the same idempotency key exists, return it."""
    if idempotency_key:
        existing = (
            await db.execute(
                select(GenerationJob).where(
                    GenerationJob.user_id == user_id, GenerationJob.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing, False
    # Prevent duplicate concurrent jobs of the same type on the same target
    active = (
        await db.execute(
            select(GenerationJob).where(
                GenerationJob.project_id == project_id,
                GenerationJob.job_type == job_type,
                GenerationJob.target_id.is_(target_id) if target_id is None else GenerationJob.target_id == target_id,
                GenerationJob.state.not_in(list(TERMINAL_STATES)),
            )
        )
    ).scalars().first()
    if active and job_type in (JobType.FULL_PIPELINE, JobType.RESEARCH, JobType.SCRIPT, JobType.SCENES):
        return active, False

    job = GenerationJob(
        project_id=project_id,
        user_id=user_id,
        job_type=job_type,
        params=params or {},
        target_id=target_id,
        parent_job_id=parent_job_id,
        idempotency_key=idempotency_key,
        timeout_seconds=timeout_seconds or settings.job_default_timeout_seconds,
        max_attempts=settings.job_max_retries,
        credits_reserved=credits_reserved,
        stage=STAGE_LABELS[JobState.QUEUED],
        message="Waiting for a worker...",
    )
    db.add(job)
    await db.flush()
    return job, True


async def create_render_job(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    width: int,
    height: int,
    fps: int,
    is_preview: bool,
    burn_captions: bool,
    include_watermark: bool,
    timeline_version: int | None,
    timeline_snapshot: dict[str, Any],
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    credits_reserved: int = 0,
) -> tuple[RenderJob, bool]:
    if idempotency_key:
        existing = (
            await db.execute(
                select(RenderJob).where(RenderJob.user_id == user_id, RenderJob.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
        if existing:
            return existing, False
    job = RenderJob(
        project_id=project_id,
        user_id=user_id,
        width=width,
        height=height,
        fps=fps,
        is_preview=is_preview,
        burn_captions=burn_captions,
        include_watermark=include_watermark,
        timeline_version=timeline_version,
        timeline_snapshot=timeline_snapshot,
        params=params or {},
        idempotency_key=idempotency_key,
        timeout_seconds=settings.render_job_timeout_seconds,
        max_attempts=2,
        credits_reserved=credits_reserved,
        stage=STAGE_LABELS[JobState.QUEUED],
        message="Waiting for a render worker...",
    )
    db.add(job)
    await db.flush()
    return job, True


async def get_job(db: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID) -> GenerationJob | RenderJob:
    job = (await db.execute(select(GenerationJob).where(GenerationJob.id == job_id))).scalar_one_or_none()
    if job is None:
        job = (await db.execute(select(RenderJob).where(RenderJob.id == job_id))).scalar_one_or_none()
    if job is None or job.user_id != user_id:
        raise NotFoundError("Job not found")
    return job


async def cancel_job(db: AsyncSession, job: GenerationJob | RenderJob) -> None:
    if job.state in TERMINAL_STATES:
        raise ConflictError(f"Job already {job.state.value.lower()}")
    job.cancel_requested = True
    await request_cancel_async(str(job.id))
    if job.state == JobState.QUEUED:
        # Not picked up yet - resolve immediately; the worker will skip it when it dequeues.
        job.state = JobState.CANCELLED
        job.finished_at = _now()
        job.message = "Cancelled before start"
        job.stage = STAGE_LABELS[JobState.CANCELLED]
        await publish_event_async(event_for(job))
    else:
        job.message = "Cancellation requested..."
        await publish_event_async(event_for(job))
    # Cancel children of a pipeline
    if isinstance(job, GenerationJob):
        children = (
            await db.execute(
                select(GenerationJob).where(
                    GenerationJob.parent_job_id == job.id, GenerationJob.state.not_in(list(TERMINAL_STATES))
                )
            )
        ).scalars().all()
        for child in children:
            child.cancel_requested = True
            await request_cancel_async(str(child.id))
    try:
        from workers.celery_app import celery_app

        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=False)
    except Exception:  # pragma: no cover
        pass


async def active_job_for_project(db: AsyncSession, project_id: uuid.UUID) -> dict[str, Any] | None:
    gen = (
        await db.execute(
            select(GenerationJob)
            .where(GenerationJob.project_id == project_id, GenerationJob.state.not_in(list(TERMINAL_STATES)))
            .order_by(GenerationJob.created_at.desc())
        )
    ).scalars().first()
    rend = (
        await db.execute(
            select(RenderJob)
            .where(RenderJob.project_id == project_id, RenderJob.state.not_in(list(TERMINAL_STATES)))
            .order_by(RenderJob.created_at.desc())
        )
    ).scalars().first()
    job = rend or gen
    if not job:
        return None
    return {
        "id": str(job.id),
        "kind": "render" if isinstance(job, RenderJob) else "generation",
        "job_type": "render" if isinstance(job, RenderJob) else job.job_type.value,
        "state": job.state.value,
        "progress": job.progress,
        "stage": job.stage,
        "message": job.message,
        "eta_seconds": job.eta_seconds,
    }


async def queue_stats(db: AsyncSession) -> dict[str, Any]:
    since = _now() - timedelta(hours=24)

    async def count(model, *conds):
        return (await db.execute(select(func.count()).select_from(model).where(*conds))).scalar_one()

    queued = await count(GenerationJob, GenerationJob.state == JobState.QUEUED) + await count(RenderJob, RenderJob.state == JobState.QUEUED)
    processing = await count(GenerationJob, GenerationJob.state.not_in([*TERMINAL_STATES, JobState.QUEUED])) + await count(
        RenderJob, RenderJob.state.not_in([*TERMINAL_STATES, JobState.QUEUED])
    )
    completed = await count(GenerationJob, GenerationJob.state == JobState.COMPLETED, GenerationJob.finished_at >= since) + await count(
        RenderJob, RenderJob.state == JobState.COMPLETED, RenderJob.finished_at >= since
    )
    failed = await count(GenerationJob, GenerationJob.state == JobState.FAILED, GenerationJob.finished_at >= since) + await count(
        RenderJob, RenderJob.state == JobState.FAILED, RenderJob.finished_at >= since
    )
    return {"queued": queued, "processing": processing, "completed_24h": completed, "failed_24h": failed}


# --------------------------------------------------------------------------- events


def event_for(job: GenerationJob | RenderJob, result: dict[str, Any] | None = None) -> dict[str, Any]:
    job_type = "render" if isinstance(job, RenderJob) else job.job_type.value
    return build_event(
        job_id=str(job.id),
        project_id=str(job.project_id),
        user_id=str(job.user_id),
        job_type=job_type,
        state=job.state.value,
        stage=job.stage,
        progress=job.progress,
        message=job.message or "",
        eta_seconds=job.eta_seconds,
        result=_serialize_result(result if result is not None else (job.result if job.state in TERMINAL_STATES else None)),
        error=job.error,
    )


# --------------------------------------------------------------------------- sync (workers)


class JobContext:
    """Handle passed to pipeline stages inside a Celery task."""

    def __init__(self, db: Session, job: GenerationJob | RenderJob, *, worker_id: str, celery_task_id: str | None = None):
        self.db = db
        self.job = job
        self.worker_id = worker_id
        self._started = _now()
        self._stage_started = self._started
        self._last_publish = 0.0
        job.worker_id = worker_id
        if celery_task_id:
            job.celery_task_id = celery_task_id

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        j = self.job
        if is_cancel_requested(str(j.id)) or j.cancel_requested:
            raise JobCancelled()
        j.attempt += 1
        j.state = JobState.PROCESSING
        j.stage = STAGE_LABELS[JobState.PROCESSING]
        j.message = "Worker picked up the job"
        j.started_at = j.started_at or _now()
        j.heartbeat_at = _now()
        j.progress = max(j.progress, 1)
        self._commit_and_publish()

    def set_state(self, state: JobState, message: str | None = None, *, progress: int | None = None) -> None:
        self.check_cancelled()
        self.job.state = state
        self.job.stage = STAGE_LABELS.get(state, state.value.title())
        self.job.message = message or f"{self.job.stage}..."
        if progress is not None:
            self.job.progress = max(self.job.progress, int(progress))
        self._stage_started = _now()
        self._commit_and_publish(force=True)

    def progress(self, percent: float, message: str | None = None, *, stage_fraction: float | None = None) -> None:
        """Update progress (0-100 overall). `message` defaults to '<stage>... NN%'."""
        self.check_cancelled()
        pct = int(max(self.job.progress if percent < self.job.progress else 0, min(99, percent)))
        self.job.progress = pct
        label = self.job.stage or "Working"
        self.job.message = message or f"{label}... {pct}%"
        self.job.heartbeat_at = _now()
        self._update_eta(stage_fraction)
        self._commit_and_publish()

    def stage_progress(self, state: JobState, fraction: float, message: str | None = None, *, base: float | None = None, weight: float | None = None) -> None:
        """Convenience: map a fraction (0-1) of a stage into overall progress using STAGE_WEIGHTS.

        For single-stage jobs (`base`/`weight` omitted) the stage spans 2% → 98%.
        """
        fraction = max(0.0, min(1.0, fraction))
        if base is None or weight is None:
            pct = 2 + fraction * 96
        else:
            pct = base + fraction * weight
        stage_label = STAGE_LABELS.get(state, state.value)
        msg = message or f"{stage_label}... {int(pct)}%"
        if self.job.state != state:
            self.job.state = state
            self.job.stage = stage_label
            self._stage_started = _now()
        self.progress(pct, msg, stage_fraction=fraction)

    def log(self, message: str, level: str = "info", **extra: Any) -> None:
        entry = {"ts": _now().isoformat(), "level": level, "message": message, **{k: str(v) for k, v in extra.items()}}
        logs = list(self.job.logs or [])
        logs.append(entry)
        self.job.logs = logs[-200:]
        getattr(log, level, log.info)(message, job_id=str(self.job.id), **extra)

    def check_cancelled(self) -> None:
        if self.job.cancel_requested or is_cancel_requested(str(self.job.id)):
            raise JobCancelled()

    def cancel_predicate(self) -> Callable[[], bool]:
        """Thread-safe `() -> bool` for long native steps (ffmpeg, provider polling).

        Only consults the Redis flag - never the ORM instance - so it may be called from
        worker threads without touching the SQLAlchemy session.
        """
        job_id = str(self.job.id)
        return lambda: is_cancel_requested(job_id)

    def complete(self, result: dict[str, Any] | None = None, message: str = "Complete") -> None:
        j = self.job
        j.state = JobState.COMPLETED
        j.stage = STAGE_LABELS[JobState.COMPLETED]
        j.progress = 100
        j.message = message
        j.finished_at = _now()
        j.eta_seconds = 0
        if result:
            j.result = {**(j.result or {}), **_serialize_result(result)}
        self._commit_and_publish(force=True)

    def fail(self, error: str, *, details: dict[str, Any] | None = None, retrying: bool = False) -> None:
        j = self.job
        j.error = error[:4000]
        j.error_details = details or {}
        if retrying:
            j.state = JobState.QUEUED
            j.stage = STAGE_LABELS[JobState.QUEUED]
            j.message = f"Attempt {j.attempt} failed - retrying: {error[:200]}"
        else:
            j.state = JobState.FAILED
            j.stage = STAGE_LABELS[JobState.FAILED]
            j.message = error[:500]
            j.finished_at = _now()
        self.log(error, level="error")
        self._commit_and_publish(force=True)

    def cancelled(self) -> None:
        j = self.job
        j.state = JobState.CANCELLED
        j.stage = STAGE_LABELS[JobState.CANCELLED]
        j.message = "Cancelled by user"
        j.finished_at = _now()
        self._commit_and_publish(force=True)

    # -- internals -------------------------------------------------------------
    def _update_eta(self, stage_fraction: float | None) -> None:
        elapsed = (_now() - self._started).total_seconds()
        pct = self.job.progress
        if pct >= 3 and elapsed > 2:
            remaining = elapsed * (100 - pct) / pct
            self.job.eta_seconds = int(min(remaining, 6 * 3600))

    def _commit_and_publish(self, force: bool = False) -> None:
        import time

        now = time.monotonic()
        if not force and now - self._last_publish < 0.4:
            return  # throttle chatty updates
        self._last_publish = now
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        try:
            publish_event(event_for(self.job))
        except Exception as exc:  # Redis hiccups must not fail the job
            log.warning("progress publish failed", error=str(exc))


def load_job_sync(db: Session, job_id: str, *, render: bool = False) -> GenerationJob | RenderJob:
    model = RenderJob if render else GenerationJob
    job = db.get(model, uuid.UUID(str(job_id)))
    if job is None:
        raise NotFoundError(f"job {job_id} not found")
    return job


def overall_progress(stage: JobState, fraction: float, stages: list[JobState]) -> float:
    """Compute overall % for a multi-stage pipeline given the ordered `stages` list."""
    total = sum(STAGE_WEIGHTS.get(s, 0.1) for s in stages) or 1.0
    done = 0.0
    for s in stages:
        w = STAGE_WEIGHTS.get(s, 0.1) / total
        if s == stage:
            done += w * max(0.0, min(1.0, fraction))
            break
        done += w
    return 2 + done * 96
