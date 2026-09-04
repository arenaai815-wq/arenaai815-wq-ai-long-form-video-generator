"""Script generation: outline -> per-section narration (parallelisable), plus section regeneration."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.enums import SectionKind, UsageKind
from app.models.project import Project, Research
from app.models.script import Script, ScriptSection
from app.models.user import User
from app.providers import get_registry
from app.providers.base import LLMResult
from app.services import prompts
from app.services.billing_service import record_usage_sync
from app.services.research_service import parse_json_result
from app.utils.text import estimate_duration_seconds, word_count

VALID_KINDS = {k.value for k in SectionKind}
MAX_PARALLEL_SECTIONS = 4


def recompute_script_stats(script: Script) -> None:
    total_words = 0
    total_secs = 0.0
    for s in script.sections:
        s.word_count = word_count(s.content)
        s.estimated_duration_seconds = estimate_duration_seconds(s.content, script.words_per_minute)
        total_words += s.word_count
        total_secs += s.estimated_duration_seconds
    script.word_count = total_words
    script.estimated_duration_seconds = round(total_secs, 2)


def current_script(db: Session, project_id: uuid.UUID) -> Script | None:
    return db.execute(
        select(Script).where(Script.project_id == project_id, Script.is_current.is_(True)).order_by(Script.version.desc())
    ).scalars().first()


def _facts_for_heading(research: Research | None, heading: str, index: int) -> list[str]:
    if not research or not research.sections:
        return list(research.key_facts[:4]) if research else []
    for sec in research.sections:
        if str(sec.get("title", "")).lower() == heading.lower():
            return list(sec.get("facts") or [])[:6]
    sec = research.sections[index % len(research.sections)]
    return list(sec.get("facts") or [])[:6]


def generate_script_sync(
    db: Session,
    project: Project,
    user: User,
    *,
    target_duration_minutes: int | None = None,
    tone: str | None = None,
    words_per_minute: int | None = None,
    instructions: str | None = None,
    job_id=None,
    progress: Callable[[float, str], None] | None = None,
) -> Script:
    llm = get_registry().llm()
    research = db.execute(select(Research).where(Research.project_id == project.id)).scalar_one_or_none()
    minutes = target_duration_minutes or project.target_duration_minutes
    tone = tone or project.tone
    wpm = words_per_minute or int((project.settings or {}).get("words_per_minute") or 150)

    if progress:
        progress(0.05, "Generating script... planning structure")
    outline_res = llm.complete(
        prompts.script_outline_prompt(
            topic=project.topic,
            title_hint=project.title,
            tone=tone,
            language=project.language,
            video_format=project.video_format,
            target_audience=project.target_audience,
            target_duration_minutes=minutes,
            words_per_minute=wpm,
            research_summary=research.summary if research else None,
            research_sections=research.sections if research else [],
            instructions=instructions,
        ),
        json_mode=True,
        temperature=0.6,
        max_tokens=3000,
    )
    outline = parse_json_result(outline_res.text, outline_res.parsed)
    planned = outline.get("sections") or []
    if not planned:
        raise ValueError("LLM returned an empty outline")

    # Retire previous version
    prev = current_script(db, project.id)
    version = (prev.version + 1) if prev else 1
    if prev:
        db.execute(update(Script).where(Script.project_id == project.id).values(is_current=False))

    script = Script(
        project_id=project.id,
        version=version,
        is_current=True,
        title=outline.get("title") or project.title,
        hook=outline.get("hook"),
        outline=planned,
        target_duration_minutes=minutes,
        words_per_minute=wpm,
        provider=outline_res.usage.provider,
        model=outline_res.usage.model,
    )
    db.add(script)
    db.flush()

    total_tokens = outline_res.usage.input_tokens + outline_res.usage.output_tokens
    n = len(planned)

    def write_one(i: int, plan: dict[str, Any]) -> tuple[int, dict[str, Any], LLMResult]:
        kind = str(plan.get("kind") or "body")
        heading = str(plan.get("heading") or f"Section {i + 1}")
        res = llm.complete(
            prompts.script_section_prompt(
                topic=project.topic,
                title=script.title,
                tone=tone,
                language=project.language,
                target_audience=project.target_audience,
                kind=kind,
                heading=heading,
                target_words=int(plan.get("target_words") or 150),
                talking_points=list(plan.get("talking_points") or []),
                facts=_facts_for_heading(research, heading, i),
                previous_summary=str(planned[i - 1].get("heading")) if i > 0 else None,
                next_heading=str(planned[i + 1].get("heading")) if i + 1 < n else None,
                instructions=instructions,
            ),
            json_mode=True,
            temperature=0.75,
            max_tokens=2500,
        )
        return i, parse_json_result(res.text, res.parsed), res

    results: dict[int, tuple[dict[str, Any], LLMResult]] = {}
    completed = 0
    # Sections are independent given the outline -> generate in parallel (bounded).
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SECTIONS) as pool:
        for i, data, res in pool.map(lambda ip: write_one(*ip), enumerate(planned)):
            results[i] = (data, res)
            completed += 1
            if progress:
                progress(0.1 + 0.85 * completed / n, f"Generating script... section {completed}/{n}")

    for i, plan in enumerate(planned):
        data, res = results[i]
        total_tokens += res.usage.input_tokens + res.usage.output_tokens
        kind = str(plan.get("kind") or "body")
        section = ScriptSection(
            script_id=script.id,
            order_index=i,
            kind=SectionKind(kind) if kind in VALID_KINDS else SectionKind.BODY,
            heading=str(data.get("heading") or plan.get("heading") or f"Section {i + 1}")[:200],
            content=str(data.get("content") or "").strip(),
            summary=data.get("summary"),
            talking_points=list(plan.get("talking_points") or []),
        )
        db.add(section)
        script.sections.append(section)
    recompute_script_stats(script)
    project.estimated_duration_seconds = script.estimated_duration_seconds
    db.flush()

    record_usage_sync(db, user, UsageKind.SCRIPT, minutes, "minutes", metrics=outline_res.usage, project_id=project.id, job_id=job_id)
    record_usage_sync(db, user, UsageKind.LLM_TOKENS, total_tokens, "tokens", metrics=outline_res.usage, project_id=project.id, job_id=job_id, charge=False)
    return script


def regenerate_section_sync(
    db: Session,
    project: Project,
    user: User,
    section: ScriptSection,
    *,
    instructions: str | None = None,
    target_words: int | None = None,
    tone: str | None = None,
    job_id=None,
) -> ScriptSection:
    llm = get_registry().llm()
    script = section.script
    research = db.execute(select(Research).where(Research.project_id == project.id)).scalar_one_or_none()
    siblings = sorted(script.sections, key=lambda s: s.order_index)
    idx = siblings.index(section)
    res = llm.complete(
        prompts.script_section_prompt(
            topic=project.topic,
            title=script.title,
            tone=tone or project.tone,
            language=project.language,
            target_audience=project.target_audience,
            kind=section.kind.value,
            heading=section.heading,
            target_words=target_words or max(40, section.word_count or 150),
            talking_points=list(section.talking_points or []),
            facts=_facts_for_heading(research, section.heading, idx),
            previous_summary=siblings[idx - 1].summary or siblings[idx - 1].heading if idx > 0 else None,
            next_heading=siblings[idx + 1].heading if idx + 1 < len(siblings) else None,
            instructions=instructions,
        ),
        json_mode=True,
        temperature=0.8,
        max_tokens=2500,
    )
    data = parse_json_result(res.text, res.parsed)
    section.content = str(data.get("content") or section.content).strip()
    section.summary = data.get("summary") or section.summary
    if data.get("heading"):
        section.heading = str(data["heading"])[:200]
    section.regeneration_count += 1
    recompute_script_stats(script)
    project.estimated_duration_seconds = script.estimated_duration_seconds
    db.flush()
    record_usage_sync(
        db, user, UsageKind.LLM_TOKENS, res.usage.input_tokens + res.usage.output_tokens, "tokens",
        metrics=res.usage, project_id=project.id, job_id=job_id, charge=False,
    )
    record_usage_sync(db, user, UsageKind.SCRIPT, 0.5, "minutes", metrics=res.usage, project_id=project.id, job_id=job_id)
    return section
