"""Job inspection, cancellation, retry and real-time progress (Server-Sent Events)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, CurrentUser, get_current_user
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.security import decode_token
from app.models.enums import TERMINAL_STATES, JobState
from app.models.job import GenerationJob, RenderJob
from app.models.project import Project
from app.models.user import User, UserSession
from app.realtime.events import JOB_CHANNEL, PROJECT_CHANNEL, USER_CHANNEL, last_event, subscribe
from app.schemas.common import Message, Page
from app.schemas.job import JobPublic, RenderJobPublic
from app.services.job_service import cancel_job, event_for, get_job
from app.services.media_service import url_for

router = APIRouter()

SSE_HEARTBEAT_SECONDS = 15


async def _public(db: AsyncSession, job: GenerationJob | RenderJob) -> JobPublic | RenderJobPublic:
    if isinstance(job, RenderJob):
        p = RenderJobPublic.model_validate(job)
        if job.output_asset_id:
            from app.models.media import MediaAsset

            a = await db.get(MediaAsset, job.output_asset_id)
            if a:
                p.output_url = url_for(a.storage_key, filename=a.filename)
        return p
    return JobPublic.model_validate(job)


async def _user_from_query_token(request: Request, db: DB, token: str | None = Query(default=None)) -> User:
    """EventSource cannot set Authorization headers, so SSE also accepts `?token=` (access JWT)."""
    if token:
        try:
            payload = decode_token(token, "access")
        except ValueError as exc:
            raise UnauthorizedError("Invalid or expired token") from exc
        session = await db.get(UserSession, uuid.UUID(payload["sid"]))
        if session is None or session.revoked_at is not None or session.expires_at < datetime.now(UTC):
            raise UnauthorizedError("Session expired or revoked")
        user = await db.get(User, uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise UnauthorizedError("Authentication required")
        request.state.user_id = str(user.id)
        return user
    from fastapi.security import HTTPAuthorizationCredentials

    auth = request.headers.get("authorization", "")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=auth.split(" ", 1)[1]) if auth.lower().startswith("bearer ") else None
    return await get_current_user(request, db, creds, request.headers.get("x-api-key"))


SSEUser = Annotated[User, Depends(_user_from_query_token)]


def _sse(event: dict[str, Any], name: str = "progress") -> str:
    return f"event: {name}\nid: {event.get('ts', '')}\ndata: {json.dumps(event)}\n\n"


async def _stream(channels: list[str], initial: list[dict[str, Any]], request: Request, *, stop_when_terminal: bool) -> AsyncIterator[str]:
    yield ": connected\n\n"
    for ev in initial:
        yield _sse(ev)
        if stop_when_terminal and ev.get("state") in {s.value for s in TERMINAL_STATES}:
            yield _sse(ev, "done")
            return
    gen = subscribe(channels)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                ev = await asyncio.wait_for(gen.__anext__(), timeout=SSE_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            except StopAsyncIteration:
                break
            yield _sse(ev)
            if stop_when_terminal and ev.get("state") in {s.value for s in TERMINAL_STATES}:
                yield _sse(ev, "done")
                break
    finally:
        await gen.aclose()


def _sse_response(it: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(it, media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# --- REST -------------------------------------------------------------------------------


@router.get("", response_model=Page[JobPublic])
async def list_jobs(user: CurrentUser, db: DB, project_id: uuid.UUID | None = None, state: JobState | None = None, active: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> Page[JobPublic]:
    gen_stmt = select(GenerationJob).where(GenerationJob.user_id == user.id)
    ren_stmt = select(RenderJob).where(RenderJob.user_id == user.id)
    if project_id:
        gen_stmt = gen_stmt.where(GenerationJob.project_id == project_id)
        ren_stmt = ren_stmt.where(RenderJob.project_id == project_id)
    if state:
        gen_stmt = gen_stmt.where(GenerationJob.state == state)
        ren_stmt = ren_stmt.where(RenderJob.state == state)
    if active:
        gen_stmt = gen_stmt.where(GenerationJob.state.not_in(list(TERMINAL_STATES)))
        ren_stmt = ren_stmt.where(RenderJob.state.not_in(list(TERMINAL_STATES)))
    gens = list((await db.execute(gen_stmt.order_by(GenerationJob.created_at.desc()).limit(500))).scalars().all())
    rens = list((await db.execute(ren_stmt.order_by(RenderJob.created_at.desc()).limit(500))).scalars().all())
    merged = sorted([*gens, *rens], key=lambda j: j.created_at, reverse=True)
    total = len(merged)
    chunk = merged[(page - 1) * page_size : page * page_size]
    items = [await _public(db, j) for j in chunk]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/events", summary="SSE stream of all job events for the current user")
async def user_events(request: Request, user: SSEUser, db: DB) -> StreamingResponse:
    active = list((await db.execute(select(GenerationJob).where(GenerationJob.user_id == user.id, GenerationJob.state.not_in(list(TERMINAL_STATES))))).scalars().all())
    active += list((await db.execute(select(RenderJob).where(RenderJob.user_id == user.id, RenderJob.state.not_in(list(TERMINAL_STATES))))).scalars().all())
    initial = [event_for(j) for j in active]
    return _sse_response(_stream([USER_CHANNEL.format(user_id=user.id)], initial, request, stop_when_terminal=False))


@router.get("/projects/{project_id}/events", summary="SSE stream of job events for one project")
async def project_events(project_id: uuid.UUID, request: Request, user: SSEUser, db: DB) -> StreamingResponse:
    project = await db.get(Project, project_id)
    if project is None or (project.owner_id != user.id and not user.is_superuser):
        raise NotFoundError("Project not found")
    active = list((await db.execute(select(GenerationJob).where(GenerationJob.project_id == project_id, GenerationJob.state.not_in(list(TERMINAL_STATES))))).scalars().all())
    active += list((await db.execute(select(RenderJob).where(RenderJob.project_id == project_id, RenderJob.state.not_in(list(TERMINAL_STATES))))).scalars().all())
    initial = [event_for(j) for j in active]
    return _sse_response(_stream([PROJECT_CHANNEL.format(project_id=project_id)], initial, request, stop_when_terminal=False))


@router.get("/{job_id}", response_model=RenderJobPublic | JobPublic)
async def get_job_route(job_id: uuid.UUID, user: CurrentUser, db: DB) -> JobPublic | RenderJobPublic:
    return await _public(db, await get_job(db, job_id, user.id))


@router.get("/{job_id}/events", summary="SSE stream for a single job (closes when the job finishes)")
async def job_events(job_id: uuid.UUID, request: Request, user: SSEUser, db: DB) -> StreamingResponse:
    job = await get_job(db, job_id, user.id)
    latest = await last_event(str(job.id))
    initial = [latest or event_for(job)]
    if job.state in TERMINAL_STATES:
        initial = [event_for(job)]
    return _sse_response(_stream([JOB_CHANNEL.format(job_id=job.id)], initial, request, stop_when_terminal=True))


@router.get("/{job_id}/logs")
async def job_logs(job_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    job = await get_job(db, job_id, user.id)
    return {"job_id": str(job.id), "logs": job.logs or [], "error": job.error, "error_details": job.error_details}


@router.post("/{job_id}/cancel", response_model=Message)
async def cancel(job_id: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    job = await get_job(db, job_id, user.id)
    await cancel_job(db, job)
    return Message(message="Cancellation requested")


@router.post("/{job_id}/retry", response_model=RenderJobPublic | JobPublic, summary="Re-queue a failed or cancelled job")
async def retry(job_id: uuid.UUID, user: CurrentUser, db: DB) -> JobPublic | RenderJobPublic:
    job = await get_job(db, job_id, user.id)
    if job.state not in (JobState.FAILED, JobState.CANCELLED):
        raise ConflictError("Only failed or cancelled jobs can be retried")
    job.state = JobState.QUEUED
    job.progress = 0
    job.error = None
    job.error_details = None
    job.cancel_requested = False
    job.finished_at = None
    job.started_at = None
    job.attempt = 0
    job.message = "Re-queued"
    job.stage = "Queued"
    await db.commit()
    if isinstance(job, RenderJob):
        from workers.tasks.render import run_render_job

        res = run_render_job.apply_async(args=[str(job.id)], queue="render")
    else:
        from workers.tasks.generation import run_generation_job, run_pipeline

        task = run_pipeline if job.job_type.value == "full_pipeline" else run_generation_job
        res = task.apply_async(args=[str(job.id)], queue="generation")
    job.celery_task_id = res.id
    await db.commit()
    return await _public(db, job)
