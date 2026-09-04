"""Celery application shared by the API (producer) and workers (consumers).

Queues
------
* ``generation`` - LLM / TTS / image / video / captions tasks (I/O heavy, high concurrency)
* ``render``     - FFmpeg composition (CPU heavy, low concurrency, dedicated workers)
* ``maintenance``- heartbeats, stale-job reaping, cleanup

Run workers with:
    celery -A workers.celery_app worker -Q generation -c 4 -n gen@%h
    celery -A workers.celery_app worker -Q render -c 1 -n render@%h
    celery -A workers.celery_app beat
"""

from __future__ import annotations

import os
import socket

from celery import Celery, signals
from celery.schedules import crontab
from kombu import Queue

from app.core.config import settings
from app.core.logging import configure_logging

celery_app = Celery("longform", broker=settings.broker_url, backend=settings.result_backend)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # a crashed worker returns the task to the queue
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long tasks: never prefetch more than one
    task_track_started=True,
    result_expires=24 * 3600,
    broker_connection_retry_on_startup=True,
    task_default_queue="generation",
    task_queues=(
        Queue("generation", routing_key="generation"),
        Queue("render", routing_key="render"),
        Queue("maintenance", routing_key="maintenance"),
    ),
    task_routes={
        "workers.tasks.render.*": {"queue": "render"},
        "workers.tasks.maintenance.*": {"queue": "maintenance"},
        "workers.tasks.generation.*": {"queue": "generation"},
    },
    task_soft_time_limit=settings.render_job_timeout_seconds,
    task_time_limit=settings.render_job_timeout_seconds + 120,
    beat_schedule={
        "worker-heartbeat": {
            "task": "workers.tasks.maintenance.heartbeat",
            "schedule": 20.0,
            "options": {"queue": "maintenance", "expires": 15},
        },
        "reap-stale-jobs": {
            "task": "workers.tasks.maintenance.reap_stale_jobs",
            "schedule": 60.0,
            "options": {"queue": "maintenance", "expires": 50},
        },
        "cleanup-work-dirs": {
            "task": "workers.tasks.maintenance.cleanup_work_dirs",
            "schedule": crontab(minute=15),
            "options": {"queue": "maintenance"},
        },
        "renew-subscriptions": {
            "task": "workers.tasks.maintenance.renew_subscription_credits",
            "schedule": crontab(minute=0, hour="*/6"),
            "options": {"queue": "maintenance"},
        },
    },
    include=["workers.tasks.generation", "workers.tasks.render", "workers.tasks.maintenance"],
)


def worker_identity() -> str:
    return os.environ.get("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"


@signals.worker_process_init.connect
def _init_worker(**_: object) -> None:
    configure_logging()
    # Fresh DB engine per forked process (never share pooled connections across forks)
    from app.db import session as db_session

    db_session._sync_engine = None
    db_session._SyncSessionLocal = None


@signals.setup_logging.connect
def _setup_logging(**_: object) -> None:
    configure_logging()
