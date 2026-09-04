"""In-process worker liveness heartbeat.

The beat-scheduled `maintenance.heartbeat` task collects rich stats through Celery's inspect
API, but it needs a free task slot to run: when every slot is busy with a long render the DB
heartbeat goes stale and the worker looks dead. This module runs a tiny daemon thread in the
worker's *main* process (started on `worker_ready`) that refreshes liveness on its own:

* Redis key  `workers:heartbeat:<nodename>`  with TTL = WORKER_HEARTBEAT_TTL_SECONDS
* `worker_heartbeats` row (hostname, queues, concurrency, last_heartbeat_at)

`GET /health/workers` and the stale-job reaper therefore stay accurate under full load.
"""
from __future__ import annotations

import os
import socket
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger

HEARTBEAT_KEY = "workers:heartbeat:{worker_id}"
log = get_logger(__name__)
_stop = threading.Event()
_thread: threading.Thread | None = None


def node_name(default: str | None = None) -> str:
    return os.environ.get("WORKER_ID") or default or f"{socket.gethostname()}-{os.getpid()}"


def _beat_once(name: str, queues: list[str], concurrency: int, version: str | None) -> None:
    from app.db.session import sync_session
    from app.models.job import WorkerHeartbeat
    from app.realtime.events import sync_redis

    now = datetime.now(UTC)
    sync_redis().setex(HEARTBEAT_KEY.format(worker_id=name), settings.worker_heartbeat_ttl_seconds, now.isoformat())
    with sync_session() as db:
        hb = db.execute(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == name)).scalar_one_or_none()
        if hb is None:
            hb = WorkerHeartbeat(worker_id=name, hostname=name.split("@")[-1], last_heartbeat_at=now)
            db.add(hb)
        hb.hostname = name.split("@")[-1]
        hb.queues = queues
        hb.concurrency = concurrency
        hb.last_heartbeat_at = now
        hb.version = version
        hb.extra = {**(hb.extra or {}), "pid": os.getpid(), "source": "thread"}
        db.commit()


def start(name: str, queues: list[str], concurrency: int, version: str | None = None) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    interval = max(5.0, settings.worker_heartbeat_ttl_seconds / 3)

    def run() -> None:
        while not _stop.is_set():
            try:
                _beat_once(name, queues, concurrency, version)
            except Exception as exc:  # never let liveness reporting crash the worker
                log.warning("heartbeat failed", worker=name, error=str(exc))
            _stop.wait(interval)

    _stop.clear()
    _thread = threading.Thread(target=run, name="worker-heartbeat", daemon=True)
    _thread.start()
    log.info("heartbeat thread started", worker=name, interval=interval)


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=2)
    try:
        from app.realtime.events import sync_redis

        sync_redis().delete(HEARTBEAT_KEY.format(worker_id=node_name()))
    except Exception:
        pass
