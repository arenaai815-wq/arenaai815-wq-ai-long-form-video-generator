from __future__ import annotations

import uuid

import anyio
from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import JobType, ProjectStatus, UsageKind
from app.models.media import Voiceover
from app.models.scene import Scene
from app.providers import get_registry
from app.schemas.job import JobPublic
from app.schemas.voiceover import VoicePreviewRequest, VoiceoverGenerateRequest, VoiceoverPublic, VoicePublic
from app.services.billing_service import assert_can_afford, credits_for_usage
from app.services.job_service import create_generation_job
from app.services.media_service import url_for

router = APIRouter()


@router.get("/voices", response_model=list[VoicePublic], summary="List available TTS voices")
async def list_voices(user: CurrentUser, language: str | None = None, provider: str | None = None) -> list[VoicePublic]:
    tts = get_registry().tts(provider)
    voices = await anyio.to_thread.run_sync(lambda: tts.list_voices(language))
    return [VoicePublic(**v.__dict__) for v in voices]


@router.post("/voices/preview", summary="Synthesize a short preview (returns audio bytes)")
@limiter.limit("20/minute")
async def preview_voice(request: Request, body: VoicePreviewRequest, user: CurrentUser) -> Response:
    tts = get_registry().tts(body.provider)
    res = await anyio.to_thread.run_sync(lambda: tts.synthesize(body.text, voice_id=body.voice_id, language=body.language, speed=body.speed, style=body.style, output_format="mp3"))
    return Response(content=res.data, media_type=res.content_type, headers={"X-Duration-Seconds": f"{res.duration_seconds:.2f}"})


@router.get("/projects/{project_id}/voiceovers", response_model=list[VoiceoverPublic])
async def list_voiceovers(project: OwnedProject, db: DB, current_only: bool = Query(True)) -> list[VoiceoverPublic]:
    stmt = select(Voiceover).where(Voiceover.project_id == project.id)
    if current_only:
        stmt = stmt.where(Voiceover.is_current.is_(True))
    rows = (await db.execute(stmt.order_by(Voiceover.created_at))).scalars().all()
    out = []
    for v in rows:
        p = VoiceoverPublic.model_validate(v)
        p.url = url_for(v.storage_key)
        out.append(p)
    return out


@router.post("/projects/{project_id}/voiceovers/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_generation)
async def generate_voiceovers(request: Request, body: VoiceoverGenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    scenes = (await db.execute(select(Scene).where(Scene.project_id == project.id))).scalars().all()
    if not scenes:
        raise ValidationError("Build the storyboard first")
    targets = [s for s in scenes if (not body.scene_ids or s.id in set(body.scene_ids)) and (body.force or not s.voiceover_id)]
    chars = sum(len(s.narration) for s in targets)
    await assert_can_afford(db, user, credits_for_usage(UsageKind.TTS_CHARACTERS, chars) if chars else 0)
    if body.voice_id:  # persist the chosen voice on the project so later regenerations match
        voice = {**((project.settings or {}).get("voice") or {})}
        voice.update({k: v for k, v in {"voice_id": body.voice_id, "provider": body.provider, "language": body.language, "style": body.style, "speed": body.speed}.items() if v is not None})
        project.settings = {**(project.settings or {}), "voice": voice}
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.VOICEOVER, params=body.model_dump(exclude_none=True, mode="json"), target_id=body.scene_ids[0] if body.scene_ids and len(body.scene_ids) == 1 else None)
    if created:
        project.status = ProjectStatus.GENERATING
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.get("/projects/{project_id}/voiceovers/{voiceover_id}", response_model=VoiceoverPublic)
async def get_voiceover(voiceover_id: uuid.UUID, project: OwnedProject, db: DB) -> VoiceoverPublic:
    v = await db.get(Voiceover, voiceover_id)
    if v is None or v.project_id != project.id:
        raise NotFoundError("Voiceover not found")
    p = VoiceoverPublic.model_validate(v)
    p.url = url_for(v.storage_key)
    return p


@router.delete("/projects/{project_id}/voiceovers/{voiceover_id}")
async def delete_voiceover(voiceover_id: uuid.UUID, project: OwnedProject, db: DB) -> dict:
    v = await db.get(Voiceover, voiceover_id)
    if v is None or v.project_id != project.id:
        raise NotFoundError("Voiceover not found")
    scenes = (await db.execute(select(Scene).where(Scene.voiceover_id == v.id))).scalars().all()
    for s in scenes:
        s.voiceover_id = None
    await db.delete(v)
    return {"message": "Voiceover deleted"}
