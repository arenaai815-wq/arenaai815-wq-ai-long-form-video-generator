"""Shared task runner: loads the job, wires the JobContext, handles retries/cancel/timeouts."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.core.exceptions import InsufficientCreditsError
from app.core.logging import get_logger
from app.db.session import sync_session
from app.models.enums import TERMINAL_STATES, JobState
from app.providers.base import ProviderPermanentError, ProviderTransientError
from app.realtime.events import clear_cancel
from app.services.job_service import JobCancelled, JobContext, load_job_sync
from workers.celery_app import worker_identity

log = get_logger(__name__)

RETRYABLE = (ProviderTransientError, ConnectionError, TimeoutError, OSError)
NON_RETRYABLE = (ProviderPermanentError, InsufficientCreditsError, ValueError, KeyError)


class Handoff(Exception):
    """Raised by a job body when it delegated the remaining work to another job (e.g. the
    pipeline queued a render). The job stays in its current non-terminal state (RENDERING)
    and the delegate is responsible for completing or failing it."""

    def __init__(self, result: dict[str, Any] | None = None):
        super().__init__("handoff")
        self.result = result or {}


def run_job(task: Task, job_id: str, body: Callable[[JobContext], dict[str, Any] | None], *, render: bool = False) -> dict[str, Any]:
    """Execute `body(ctx)` for the given job with full lifecycle handling.

    Idempotent: if the job is already terminal (e.g. duplicate delivery after a broker
    restart) we return immediately without re-running side effects.
    """
    with sync_session() as db:
        job = load_job_sync(db, job_id, render=render)
        if job.state in TERMINAL_STATES:
            log.info("job already terminal, skipping", job_id=job_id, state=job.state.value)
            return {"job_id": job_id, "state": job.state.value, "skipped": True}
        ctx = JobContext(db, job, worker_id=worker_identity(), celery_task_id=task.request.id)
        try:
            ctx.start()
            result = body(ctx) or {}
            ctx.complete(result)
            clear_cancel(job_id)
            return {"job_id": job_id, "state": JobState.COMPLETED.value, **{k: str(v) for k, v in result.items()}}
        except Handoff as h:
            # Persist what we have; the delegate job finishes the lifecycle (see render.run_render_job).
            job.result = {**(job.result or {}), **h.result}
            db.commit()
            log.info("job handed off", job_id=job_id, state=job.state.value)
            return {"job_id": job_id, "state": job.state.value, "handoff": True}
        except JobCancelled:
            db.rollback()
            job = load_job_sync(db, job_id, render=render)
            ctx.job = job
            ctx.cancelled()
            clear_cancel(job_id)
            return {"job_id": job_id, "state": JobState.CANCELLED.value}
        except SoftTimeLimitExceeded:
            db.rollback()
            job = load_job_sync(db, job_id, render=render)
            ctx.job = job
            ctx.fail(f"Job exceeded its time limit of {job.timeout_seconds}s")
            return {"job_id": job_id, "state": JobState.FAILED.value}
        except NON_RETRYABLE as exc:
            db.rollback()
            job = load_job_sync(db, job_id, render=render)
            ctx.job = job
            # These are deliberate, human-readable failures (bad input, missing media, provider
            # refusal, no credits): surface the message itself; the class name goes to details.
            msg = str(exc).strip() or exc.__class__.__name__
            ctx.fail(msg, details={"type": exc.__class__.__name__, "traceback": traceback.format_exc()[-3000:]})
            return {"job_id": job_id, "state": JobState.FAILED.value}
        except Exception as exc:  # retryable / unknown
            db.rollback()
            job = load_job_sync(db, job_id, render=render)
            ctx.job = job
            will_retry = job.attempt < job.max_attempts and isinstance(exc, RETRYABLE + (RuntimeError,))
            ctx.fail(f"{exc.__class__.__name__}: {exc}", details={"traceback": traceback.format_exc()[-3000:]}, retrying=will_retry)
            if will_retry:
                countdown = min(300, 10 * (2 ** (job.attempt - 1)))
                log.warning("retrying job", job_id=job_id, attempt=job.attempt, countdown=countdown)
                raise task.retry(exc=exc, countdown=countdown, max_retries=job.max_attempts) from exc
            return {"job_id": job_id, "state": JobState.FAILED.value}
