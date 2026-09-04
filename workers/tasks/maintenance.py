"""Operational tasks: heartbeats, stale job reaping, cleanup, subscription renewals."""

from __future__ import annotations

import shutil
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import sync_session
from app.models.billing import Subscription
from app.models.enums import TERMINAL_STATES, CreditTransactionKind, JobState, SubscriptionStatus
from app.models.job import GenerationJob, RenderJob, WorkerHeartbeat
from app.models.user import User
from app.realtime.events import publish_event, sync_redis
from app.services.billing_service import add_credits_sync
from app.services.job_service import event_for
from workers.celery_app import celery_app
from workers.heartbeat import HEARTBEAT_KEY

log = get_logger(__name__)


@celery_app.task(name="workers.tasks.maintenance.heartbeat")
def heartbeat() -> dict:
    """Record liveness for every worker reachable via Celery's inspect API + this process."""
    now = datetime.now(UTC)
    stats = {}
    try:
        insp = celery_app.control.inspect(timeout=2.0)
        stats = insp.stats() or {}
        active = insp.active() or {}
        queues = insp.active_queues() or {}
    except Exception as exc:  # pragma: no cover
        log.warning("inspect failed", error=str(exc))
        active, queues = {}, {}
    seen = []
    with sync_session() as db:
        for name, st in stats.items():
            hb = db.execute(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == name)).scalar_one_or_none()
            if hb is None:
                hb = WorkerHeartbeat(worker_id=name, hostname=name.split("@")[-1], last_heartbeat_at=now)
                db.add(hb)
            pool = st.get("pool", {})
            hb.hostname = name.split("@")[-1]
            hb.queues = [q["name"] for q in queues.get(name, [])]
            hb.concurrency = int(pool.get("max-concurrency") or 1)
            hb.active_tasks = len(active.get(name, []))
            totals = st.get("total", {})
            hb.processed_total = int(sum(totals.values())) if isinstance(totals, dict) else 0
            hb.last_heartbeat_at = now
            hb.version = st.get("sw_ver")
            hb.extra = {"pid": st.get("pid"), "uptime": st.get("uptime")}
            seen.append(name)
            sync_redis().setex(HEARTBEAT_KEY.format(worker_id=name), settings.worker_heartbeat_ttl_seconds, now.isoformat())
    return {"workers": seen, "ts": now.isoformat()}


@celery_app.task(name="workers.tasks.maintenance.reap_stale_jobs")
def reap_stale_jobs() -> dict:
    """Fail jobs whose worker stopped heart-beating (crash, OOM, node loss) so users are not stuck."""
    now = datetime.now(UTC)
    reaped = []
    with sync_session() as db:
        for model in (GenerationJob, RenderJob):
            rows = db.execute(select(model).where(model.state.not_in(list(TERMINAL_STATES) + [JobState.QUEUED]))).scalars().all()
            for job in rows:
                last = job.heartbeat_at or job.started_at or job.queued_at
                limit = timedelta(seconds=max(300, job.timeout_seconds + 120))
                stale_hb = (now - last) > timedelta(seconds=max(180, settings.worker_heartbeat_ttl_seconds * 6))
                timed_out = job.started_at and (now - job.started_at) > limit
                if not (stale_hb or timed_out):
                    continue
                # Only reap if the worker itself is gone (avoid killing long single-step ffmpeg encodes)
                worker_alive = bool(job.worker_id and sync_redis().exists(HEARTBEAT_KEY.format(worker_id=job.worker_id)))
                if stale_hb and worker_alive and not timed_out:
                    continue
                job.state = JobState.FAILED
                job.error = "Worker lost or job timed out" if not timed_out else f"Timed out after {job.timeout_seconds}s"
                job.message = job.error
                job.stage = "Failed"
                job.finished_at = now
                reaped.append(str(job.id))
                try:
                    publish_event(event_for(job))
                except Exception:
                    pass
            # Queued jobs that never got picked up within 2x timeout
            queued = db.execute(select(model).where(model.state == JobState.QUEUED)).scalars().all()
            for job in queued:
                if (now - job.queued_at) > timedelta(seconds=job.timeout_seconds * 2 + 3600):
                    job.state = JobState.FAILED
                    job.error = "No worker picked up this job"
                    job.message = job.error
                    job.finished_at = now
                    reaped.append(str(job.id))
                    try:
                        publish_event(event_for(job))
                    except Exception:
                        pass
    if reaped:
        log.warning("reaped stale jobs", count=len(reaped))
    return {"reaped": reaped}


@celery_app.task(name="workers.tasks.maintenance.cleanup_work_dirs")
def cleanup_work_dirs(max_age_hours: int = 12) -> dict:
    root = Path(settings.render_work_dir)
    removed = 0
    if root.exists():
        cutoff = time.time() - max_age_hours * 3600
        for d in root.iterdir():
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
    return {"removed": removed}


@celery_app.task(name="workers.tasks.maintenance.renew_subscription_credits")
def renew_subscription_credits() -> dict:
    """Grant monthly credits when a billing period rolls over (idempotent per period)."""
    now = datetime.now(UTC)
    renewed = 0
    with sync_session() as db:
        subs = db.execute(select(Subscription).where(Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]))).scalars().all()
        for sub in subs:
            if sub.current_period_end and sub.current_period_end <= now:
                user = db.get(User, sub.user_id)
                if not user:
                    continue
                period_ref = f"renewal:{sub.id}:{sub.current_period_end.date().isoformat()}"
                add_credits_sync(db, user, sub.monthly_credits, CreditTransactionKind.SUBSCRIPTION_RENEWAL, description=f"Monthly credits ({sub.plan.value})", reference=period_ref)
                sub.current_period_start = now
                sub.current_period_end = now + timedelta(days=30)
                renewed += 1
    return {"renewed": renewed}


__all__ = ["heartbeat", "reap_stale_jobs", "cleanup_work_dirs", "renew_subscription_credits", "socket"]
