from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import JobType, ProjectStatus, UsageKind
from app.models.script import Script, ScriptSection
from app.schemas.common import Message
from app.schemas.job import JobPublic
from app.schemas.script import (
    ScriptGenerateRequest,
    ScriptPublic,
    ScriptStats,
    ScriptUpdate,
    SectionCreate,
    SectionRegenerateRequest,
    SectionReorder,
    SectionUpdate,
)
from app.services.billing_service import assert_can_afford, credits_for_usage
from app.services.job_service import create_generation_job
from app.utils.text import estimate_duration_seconds, word_count

router = APIRouter()


async def _current(db: DB, project_id: uuid.UUID, *, required: bool = True) -> Script | None:
    s = (
        await db.execute(
            select(Script).where(Script.project_id == project_id, Script.is_current.is_(True)).options(selectinload(Script.sections)).order_by(Script.version.desc())
        )
    ).scalars().first()
    if s is None and required:
        raise NotFoundError("No script yet. Generate one first.")
    return s


def _recompute(script: Script) -> None:
    tw, ts = 0, 0.0
    for sec in script.sections:
        sec.word_count = word_count(sec.content)
        sec.estimated_duration_seconds = estimate_duration_seconds(sec.content, script.words_per_minute)
        tw += sec.word_count
        ts += sec.estimated_duration_seconds
    script.word_count = tw
    script.estimated_duration_seconds = round(ts, 2)


@router.get("", response_model=ScriptPublic)
async def get_script(project: OwnedProject, db: DB) -> Script:
    return await _current(db, project.id)


@router.get("/versions", response_model=list[ScriptPublic])
async def script_versions(project: OwnedProject, db: DB) -> list[Script]:
    return list((await db.execute(select(Script).where(Script.project_id == project.id).options(selectinload(Script.sections)).order_by(Script.version.desc()))).scalars().all())


@router.post("/versions/{version}/restore", response_model=ScriptPublic)
async def restore_version(version: int, project: OwnedProject, db: DB) -> Script:
    target = (await db.execute(select(Script).where(Script.project_id == project.id, Script.version == version).options(selectinload(Script.sections)))).scalar_one_or_none()
    if target is None:
        raise NotFoundError("Version not found")
    for s in (await db.execute(select(Script).where(Script.project_id == project.id))).scalars():
        s.is_current = s.id == target.id
    return target


@router.get("/stats", response_model=ScriptStats)
async def script_stats(project: OwnedProject, db: DB) -> ScriptStats:
    s = await _current(db, project.id)
    target = s.target_duration_minutes * 60
    return ScriptStats(word_count=s.word_count, estimated_duration_seconds=s.estimated_duration_seconds, target_duration_seconds=target, sections=len(s.sections), words_per_minute=s.words_per_minute, delta_seconds=round(s.estimated_duration_seconds - target, 1))


@router.post("/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_generation)
async def generate_script(request: Request, body: ScriptGenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    minutes = body.target_duration_minutes or project.target_duration_minutes
    await assert_can_afford(db, user, credits_for_usage(UsageKind.SCRIPT, minutes))
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.SCRIPT, params=body.model_dump(exclude_none=True))
    if created:
        project.status = ProjectStatus.SCRIPTING
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.patch("", response_model=ScriptPublic)
async def update_script(body: ScriptUpdate, project: OwnedProject, db: DB) -> Script:
    s = await _current(db, project.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    _recompute(s)
    project.estimated_duration_seconds = s.estimated_duration_seconds
    return s


# --- sections ---------------------------------------------------------------------------


async def _section(db: DB, script: Script, section_id: uuid.UUID) -> ScriptSection:
    for sec in script.sections:
        if sec.id == section_id:
            return sec
    raise NotFoundError("Section not found")


@router.post("/sections", response_model=ScriptPublic, status_code=status.HTTP_201_CREATED)
async def add_section(body: SectionCreate, project: OwnedProject, db: DB) -> Script:
    s = await _current(db, project.id)
    ordered = sorted(s.sections, key=lambda x: x.order_index)
    insert_at = len(ordered)
    if body.after_section_id:
        for i, sec in enumerate(ordered):
            if sec.id == body.after_section_id:
                insert_at = i + 1
    new = ScriptSection(script_id=s.id, order_index=insert_at, kind=body.kind, heading=body.heading, content=body.content, talking_points=body.talking_points)
    ordered.insert(insert_at, new)
    for i, sec in enumerate(ordered):
        sec.order_index = i
    db.add(new)
    s.sections.append(new)
    _recompute(s)
    await db.flush()
    await db.refresh(s, attribute_names=["sections"])
    return s


@router.patch("/sections/{section_id}", response_model=ScriptPublic)
async def update_section(section_id: uuid.UUID, body: SectionUpdate, project: OwnedProject, db: DB) -> Script:
    s = await _current(db, project.id)
    sec = await _section(db, s, section_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(sec, k, v)
    _recompute(s)
    project.estimated_duration_seconds = s.estimated_duration_seconds
    return s


@router.delete("/sections/{section_id}", response_model=ScriptPublic)
async def delete_section(section_id: uuid.UUID, project: OwnedProject, db: DB) -> Script:
    s = await _current(db, project.id)
    sec = await _section(db, s, section_id)
    if len(s.sections) <= 1:
        raise ValidationError("A script needs at least one section")
    s.sections.remove(sec)
    await db.delete(sec)
    for i, x in enumerate(sorted(s.sections, key=lambda x: x.order_index)):
        x.order_index = i
    _recompute(s)
    await db.flush()
    return s


@router.post("/sections/reorder", response_model=ScriptPublic)
async def reorder_sections(body: SectionReorder, project: OwnedProject, db: DB) -> Script:
    s = await _current(db, project.id)
    by_id = {sec.id: sec for sec in s.sections}
    if set(body.section_ids) != set(by_id):
        raise ValidationError("section_ids must contain every section exactly once")
    for i, sid in enumerate(body.section_ids):
        by_id[sid].order_index = i
    await db.flush()
    await db.refresh(s, attribute_names=["sections"])
    return s


@router.post("/sections/{section_id}/regenerate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_generation)
async def regenerate_section(request: Request, section_id: uuid.UUID, body: SectionRegenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    s = await _current(db, project.id)
    sec = await _section(db, s, section_id)
    if sec.is_locked:
        raise ValidationError("Section is locked. Unlock it to regenerate.")
    await assert_can_afford(db, user, credits_for_usage(UsageKind.SCRIPT, 0.5))
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.SCRIPT_SECTION, params=body.model_dump(exclude_none=True), target_id=sec.id)
    if created:
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.post("/sections/{section_id}/lock", response_model=Message)
async def toggle_lock(section_id: uuid.UUID, project: OwnedProject, db: DB, locked: bool = True) -> Message:
    s = await _current(db, project.id)
    sec = await _section(db, s, section_id)
    sec.is_locked = locked
    return Message(message="Section locked" if locked else "Section unlocked")
