from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import JobType
from app.models.media import Caption
from app.models.scene import Scene
from app.schemas.caption import CaptionGenerateRequest, CaptionPublic, CaptionUpdate
from app.schemas.job import JobPublic
from app.services.caption_service import DEFAULT_STYLE, to_srt, to_vtt, write_caption_files
from app.services.job_service import create_generation_job
from app.services.media_service import url_for

router = APIRouter()


async def _current(db: DB, project_id) -> Caption:
    c = (await db.execute(select(Caption).where(Caption.project_id == project_id, Caption.is_current.is_(True)).order_by(Caption.created_at.desc()))).scalars().first()
    if c is None:
        raise NotFoundError("No captions yet. Generate them first.")
    return c


def _public(c: Caption) -> CaptionPublic:
    p = CaptionPublic.model_validate(c)
    p.srt_url = url_for(c.srt_storage_key, filename="captions.srt")
    p.vtt_url = url_for(c.vtt_storage_key, filename="captions.vtt")
    return p


@router.get("", response_model=CaptionPublic)
async def get_captions(project: OwnedProject, db: DB) -> CaptionPublic:
    return _public(await _current(db, project.id))


@router.post("/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_generation)
async def generate_captions(request: Request, body: CaptionGenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    n = (await db.execute(select(Scene.id).where(Scene.project_id == project.id))).first()
    if n is None:
        raise ValidationError("Build the storyboard and voiceover first")
    params = body.model_dump(exclude_none=True, mode="json")
    if body.style:
        params["style"] = body.style.model_dump(mode="json")
        project.settings = {**(project.settings or {}), "captions": params["style"]}
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.CAPTIONS, params=params)
    if created:
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.put("", response_model=CaptionPublic)
async def update_captions(body: CaptionUpdate, project: OwnedProject, user: CurrentUser, db: DB) -> CaptionPublic:
    c = await _current(db, project.id)
    if body.cues is not None:
        cues = [cue.model_dump(mode="json") for cue in body.cues]
        for i, cue in enumerate(cues, 1):
            cue["index"] = i
        c.cues = cues
        c.cue_count = len(cues)
    if body.style is not None:
        c.style = {**DEFAULT_STYLE, **body.style.model_dump(mode="json")}
        project.settings = {**(project.settings or {}), "captions": c.style}
    if body.language:
        c.language = body.language
    await db.flush()
    await db.run_sync(lambda _s: write_caption_files(c, user.id, project.id))
    return _public(c)


@router.get("/export.{fmt}", summary="Download captions as SRT or VTT")
async def export_captions(fmt: str, project: OwnedProject, db: DB) -> Response:
    c = await _current(db, project.id)
    st = {**DEFAULT_STYLE, **(c.style or {})}
    mc, ml = int(st["max_chars_per_line"]), int(st["max_lines"])
    if fmt == "srt":
        return Response(to_srt(c.cues, mc, ml), media_type="application/x-subrip", headers={"Content-Disposition": 'attachment; filename="captions.srt"'})
    if fmt == "vtt":
        return Response(to_vtt(c.cues, mc, ml), media_type="text/vtt", headers={"Content-Disposition": 'attachment; filename="captions.vtt"'})
    raise ValidationError("fmt must be srt or vtt")
