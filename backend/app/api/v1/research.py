from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, OwnedProject, limiter
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.enums import JobType, ProjectStatus, UsageKind
from app.models.project import Research
from app.schemas.job import JobPublic
from app.schemas.research import ResearchGenerateRequest, ResearchPublic, ResearchUpdate
from app.services.billing_service import assert_can_afford, credits_for_usage
from app.services.job_service import create_generation_job

router = APIRouter()


@router.get("", response_model=ResearchPublic)
async def get_research(project: OwnedProject, db: DB) -> Research:
    r = (await db.execute(select(Research).where(Research.project_id == project.id))).scalar_one_or_none()
    if r is None:
        raise NotFoundError("No research yet. Generate it first.")
    return r


@router.post("/generate", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.rate_limit_generation)
async def generate_research(request: Request, body: ResearchGenerateRequest, project: OwnedProject, user: CurrentUser, db: DB) -> JobPublic:
    await assert_can_afford(db, user, credits_for_usage(UsageKind.RESEARCH, 1))
    job, created = await create_generation_job(db, project_id=project.id, user_id=user.id, job_type=JobType.RESEARCH, params=body.model_dump())
    if created:
        project.status = ProjectStatus.RESEARCHING
        await db.commit()
        from workers.tasks.generation import run_generation_job

        res = run_generation_job.apply_async(args=[str(job.id)], queue="generation")
        job.celery_task_id = res.id
    return JobPublic.model_validate(job)


@router.put("", response_model=ResearchPublic)
async def update_research(body: ResearchUpdate, project: OwnedProject, db: DB) -> Research:
    r = (await db.execute(select(Research).where(Research.project_id == project.id))).scalar_one_or_none()
    if r is None:
        r = Research(project_id=project.id)
        db.add(r)
    data = body.model_dump(exclude_unset=True, mode="json")
    approved = data.pop("approved", None)
    for k, v in data.items():
        if v is not None:
            setattr(r, k, v)
    if approved is True:
        r.approved_at = datetime.now(UTC)
        if project.status in (ProjectStatus.DRAFT, ProjectStatus.RESEARCHING):
            project.status = ProjectStatus.SCRIPTING
    elif approved is False:
        r.approved_at = None
    await db.flush()
    return r
