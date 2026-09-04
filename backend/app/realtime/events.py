"""Progress event bus.

Workers publish `JobProgressEvent`s (see shared/schemas/progress_event.json) to Redis
channels; the API relays them to browsers over Server-Sent Events. Events are also
mirrored into a short-lived Redis key so a client that connects late gets the latest
state immediately.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import redis
import redis.asyncio as aioredis

from app.core.config import settings

JOB_CHANNEL = "jobs:{job_id}"
PROJECT_CHANNEL = "projects:{project_id}"
USER_CHANNEL = "users:{user_id}"
LAST_EVENT_KEY = "jobs:{job_id}:last"
CANCEL_KEY = "jobs:{job_id}:cancel"

_sync_client: redis.Redis | None = None
_async_client: aioredis.Redis | None = None


def sync_redis() -> redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _sync_client


def async_redis() -> aioredis.Redis:
    global _async_client
    if _async_client is None:
        _async_client = aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _async_client


def build_event(
    *,
    job_id: str,
    project_id: str,
    user_id: str | None,
    job_type: str,
    state: str,
    progress: int,
    message: str,
    stage: str | None = None,
    eta_seconds: int | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "job_id": str(job_id),
        "project_id": str(project_id),
        "user_id": str(user_id) if user_id else None,
        "job_type": job_type,
        "state": state,
        "stage": stage or "",
        "progress": int(max(0, min(100, progress))),
        "message": message,
        "eta_seconds": eta_seconds,
        "result": result,
        "error": error,
        "ts": datetime.now(UTC).isoformat(),
    }


def publish_event(event: dict[str, Any]) -> None:
    """Publish from a worker (sync)."""
    r = sync_redis()
    payload = json.dumps(event)
    pipe = r.pipeline()
    pipe.publish(JOB_CHANNEL.format(job_id=event["job_id"]), payload)
    pipe.publish(PROJECT_CHANNEL.format(project_id=event["project_id"]), payload)
    if event.get("user_id"):
        pipe.publish(USER_CHANNEL.format(user_id=event["user_id"]), payload)
    pipe.setex(LAST_EVENT_KEY.format(job_id=event["job_id"]), 3600, payload)
    pipe.execute()


async def publish_event_async(event: dict[str, Any]) -> None:
    r = async_redis()
    payload = json.dumps(event)
    async with r.pipeline() as pipe:
        pipe.publish(JOB_CHANNEL.format(job_id=event["job_id"]), payload)
        pipe.publish(PROJECT_CHANNEL.format(project_id=event["project_id"]), payload)
        if event.get("user_id"):
            pipe.publish(USER_CHANNEL.format(user_id=event["user_id"]), payload)
        pipe.setex(LAST_EVENT_KEY.format(job_id=event["job_id"]), 3600, payload)
        await pipe.execute()


async def last_event(job_id: str) -> dict[str, Any] | None:
    raw = await async_redis().get(LAST_EVENT_KEY.format(job_id=job_id))
    return json.loads(raw) if raw else None


async def subscribe(channels: list[str], *, heartbeat: float | None = None) -> AsyncIterator[dict[str, Any] | None]:
    """Async generator yielding parsed events from one or more channels.

    When `heartbeat` is set, `None` is yielded whenever no message arrived within that many
    seconds so callers can emit keep-alives *without* cancelling this generator (cancelling
    a pending `__anext__()` with `asyncio.wait_for` would finalize the generator and silently
    end the stream - a classic SSE bug).
    """
    r = async_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(*channels)
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=heartbeat if heartbeat else 1.0)
            if msg is None:
                if heartbeat:
                    yield None
                continue
            if msg.get("type") != "message":
                continue
            try:
                yield json.loads(msg["data"])
            except (TypeError, json.JSONDecodeError):
                continue
    finally:
        try:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()
        except Exception:
            pass


# --- cancellation flags -----------------------------------------------------


def request_cancel(job_id: str) -> None:
    sync_redis().setex(CANCEL_KEY.format(job_id=job_id), 24 * 3600, "1")


async def request_cancel_async(job_id: str) -> None:
    await async_redis().setex(CANCEL_KEY.format(job_id=job_id), 24 * 3600, "1")


def is_cancel_requested(job_id: str) -> bool:
    return bool(sync_redis().exists(CANCEL_KEY.format(job_id=job_id)))


def clear_cancel(job_id: str) -> None:
    sync_redis().delete(CANCEL_KEY.format(job_id=job_id))
