"""AI research generation (worker-side) and helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ProviderError
from app.models.enums import UsageKind
from app.models.project import Project, Research
from app.models.user import User
from app.providers import get_registry
from app.services import prompts
from app.services.billing_service import record_usage_sync


def parse_json_result(text: str, parsed: Any | None) -> dict[str, Any]:
    if isinstance(parsed, dict):
        return parsed
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise ProviderError("LLM returned non-JSON output") from None


def generate_research_sync(
    db: Session,
    project: Project,
    user: User,
    *,
    section_count: int = 6,
    depth: str = "standard",
    focus: str | None = None,
    include_sources: bool = True,
    job_id=None,
    progress=None,
) -> Research:
    llm = get_registry().llm()
    messages = prompts.research_prompt(
        topic=project.topic,
        niche=project.niche,
        target_audience=project.target_audience,
        language=project.language,
        tone=project.tone,
        video_format=project.video_format,
        target_duration_minutes=project.target_duration_minutes,
        section_count=section_count,
        depth=depth,
        focus=focus,
        include_sources=include_sources,
    )
    if progress:
        progress(0.15, "Researching topic... querying knowledge sources")
    result = llm.complete(messages, json_mode=True, temperature=0.4, max_tokens=6000)
    data = parse_json_result(result.text, result.parsed)
    if progress:
        progress(0.8, "Researching topic... organising findings")

    research = db.execute(select(Research).where(Research.project_id == project.id)).scalar_one_or_none()
    if research is None:
        research = Research(project_id=project.id)
        db.add(research)
    research.summary = data.get("summary")
    research.sections = data.get("sections") or []
    research.key_facts = data.get("key_facts") or []
    research.statistics = data.get("statistics") or []
    research.sources = data.get("sources") or []
    research.suggested_angles = data.get("suggested_angles") or []
    research.keywords = data.get("keywords") or []
    research.provider = result.usage.provider
    research.model = result.usage.model
    research.approved_at = None
    db.flush()

    record_usage_sync(db, user, UsageKind.RESEARCH, 1, "research", metrics=result.usage, project_id=project.id, job_id=job_id)
    record_usage_sync(
        db, user, UsageKind.LLM_TOKENS, result.usage.input_tokens + result.usage.output_tokens, "tokens",
        metrics=result.usage, project_id=project.id, job_id=job_id, charge=False,
    )
    return research
