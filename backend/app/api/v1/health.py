from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select, text

from app.api.deps import DB
from app.core.config import settings
from app.models.job import WorkerHeartbeat
from app.providers import get_registry
from app.realtime.events import async_redis
from app.schemas.job import WorkerStatus
from app.services.job_service import queue_stats
from app.storage import get_storage

router = APIRouter()


@router.get("/health", summary="Liveness/readiness probe")
async def health(db: DB) -> dict:
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
    try:
        await async_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"
    checks["storage"] = "ok" if get_storage().health() else "error"
    ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if ok else "degraded", "environment": settings.environment, "checks": checks, "providers": get_registry().active(), "ts": datetime.now(UTC).isoformat()}


@router.get("/health/workers", response_model=list[WorkerStatus], summary="Worker health")
async def workers(db: DB) -> list[WorkerStatus]:
    rows = (await db.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.worker_id))).scalars().all()
    threshold = datetime.now(UTC) - timedelta(seconds=settings.worker_heartbeat_ttl_seconds * 3)
    return [
        WorkerStatus(
            worker_id=w.worker_id, hostname=w.hostname, queues=list(w.queues or []), concurrency=w.concurrency,
            active_tasks=w.active_tasks, processed_total=w.processed_total, failed_total=w.failed_total,
            last_heartbeat_at=w.last_heartbeat_at, healthy=w.last_heartbeat_at >= threshold, version=w.version,
        )
        for w in rows
    ]


@router.get("/health/queues", summary="Queue depth and throughput")
async def queues(db: DB) -> dict:
    stats = await queue_stats(db)
    depths: dict[str, int] = {}
    try:
        r = async_redis()
        for q in ("generation", "render", "maintenance"):
            depths[q] = int(await r.llen(q))
    except Exception:
        pass
    workers_online = 0
    try:
        threshold = datetime.now(UTC) - timedelta(seconds=settings.worker_heartbeat_ttl_seconds * 3)
        rows = (await db.execute(select(WorkerHeartbeat).where(WorkerHeartbeat.last_heartbeat_at >= threshold))).scalars().all()
        workers_online = len(rows)
    except Exception:
        pass
    return {**stats, "workers_online": workers_online, "queue_depths": depths}
