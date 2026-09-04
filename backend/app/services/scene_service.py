"""Storyboard generation: split script sections into scenes and design visuals for each."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.enums import UsageKind, VisualType
from app.models.project import Project
from app.models.scene import Scene
from app.models.script import Script
from app.models.user import User
from app.providers import get_registry
from app.services import prompts
from app.services.billing_service import record_usage_sync
from app.services.research_service import parse_json_result
from app.utils.text import chunk_text, estimate_duration_seconds, split_sentences, wpm_for_tone

VALID_TRANSITIONS = {"none", "fade", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "circleopen", "fadeblack", "fadewhite", "smoothleft", "smoothright"}
VALID_EFFECTS = {"none", "ken_burns", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"}


def chunk_narration(text: str, target_seconds: float, wpm: int) -> list[str]:
    """Split narration into scene-sized chunks (~target_seconds each) on sentence boundaries."""
    target_words = max(12, int(target_seconds * wpm / 60))
    max_chars = int(target_words * 6.2)
    chunks = chunk_text(text, max_chars)
    min_words = max(6, target_words // 3)
    # Merge tiny chunks into a neighbour so no scene is just "Picture this."
    merged: list[str] = []
    carry = ""
    for c in chunks:
        if carry:
            c = f"{carry} {c}"
            carry = ""
        if len(c.split()) < min_words:
            if merged and len(merged[-1].split()) <= target_words:
                merged[-1] = f"{merged[-1]} {c}"
            else:
                carry = c  # prepend to the next chunk
        else:
            merged.append(c)
    if carry:
        if merged:
            merged[-1] = f"{merged[-1]} {carry}"
        else:
            merged.append(carry)
    return merged or ([text.strip()] if text.strip() else [])


def visual_type_for(project: Project, index: int, total: int) -> VisualType:
    mode = ((project.settings or {}).get("visuals") or {}).get("mode", "ai_image")
    if mode == "ai_video":
        return VisualType.AI_VIDEO
    if mode == "stock":
        return VisualType.STOCK_VIDEO
    if mode == "mixed":
        ratio = float(((project.settings or {}).get("visuals") or {}).get("ai_video_ratio") or 0.25)
        step = max(1, int(round(1 / ratio))) if ratio > 0 else 10**9
        return VisualType.AI_VIDEO if index % step == 0 else VisualType.AI_IMAGE
    return VisualType.AI_IMAGE


def generate_scenes_sync(
    db: Session,
    project: Project,
    user: User,
    script: Script,
    *,
    scene_target_seconds: float | None = None,
    job_id=None,
    progress: Callable[[float, str], None] | None = None,
) -> list[Scene]:
    llm = get_registry().llm()
    settings_ = project.settings or {}
    target = float(scene_target_seconds or settings_.get("scene_target_seconds") or 9.0)
    wpm = int(script.words_per_minute or wpm_for_tone(project.tone))
    default_transition = (settings_.get("visuals") or {}).get("transition", "fade")
    default_effect = (settings_.get("visuals") or {}).get("motion", "ken_burns")
    transition_duration = float((settings_.get("visuals") or {}).get("transition_duration") or 0.6)

    sections = sorted(script.sections, key=lambda s: s.order_index)
    plan: list[tuple[int, object, list[str]]] = []
    for sec in sections:
        chunks = chunk_narration(sec.content, target, wpm)
        if chunks:
            plan.append((len(plan), sec, chunks))
    total_chunks = sum(len(c) for _, _, c in plan) or 1

    # Replace previous storyboard (visual assets remain in the media library)
    db.execute(delete(Scene).where(Scene.project_id == project.id))
    db.flush()

    def design(item):
        i, sec, chunks = item
        res = llm.complete(
            prompts.scene_breakdown_prompt(
                topic=project.topic,
                visual_style=project.visual_style,
                aspect_ratio=project.aspect_ratio,
                heading=sec.heading,
                chunks=chunks,
                previous_visual=None,
            ),
            json_mode=True,
            temperature=0.7,
            max_tokens=4000,
        )
        data = parse_json_result(res.text, res.parsed)
        return i, sec, chunks, data, res

    designed = {}
    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, sec, chunks, data, res in pool.map(design, plan):
            designed[i] = (sec, chunks, data, res)
            done += len(chunks)
            if progress:
                progress(0.1 + 0.8 * done / total_chunks, f"Building storyboard... {done}/{total_chunks} scenes")

    scenes: list[Scene] = []
    order = 0
    tokens = 0
    for i in range(len(plan)):
        sec, chunks, data, res = designed[i]
        tokens += res.usage.input_tokens + res.usage.output_tokens
        gen = list(data.get("scenes") or [])
        for j, chunk in enumerate(chunks):
            g = gen[j] if j < len(gen) else {}
            transition = str(g.get("transition") or default_transition)
            effect = str(g.get("motion_effect") or default_effect)
            scene = Scene(
                project_id=project.id,
                section_id=sec.id,
                order_index=order,
                title=str(g.get("title") or f"{sec.heading} ({j + 1})")[:200],
                narration=chunk,  # always trust the script, never the LLM echo
                visual_description=g.get("visual_description"),
                suggested_footage=g.get("suggested_footage"),
                image_prompt=g.get("image_prompt") or f"{project.visual_style} illustration of: {split_sentences(chunk)[0] if split_sentences(chunk) else chunk[:100]}",
                video_prompt=g.get("video_prompt"),
                negative_prompt=g.get("negative_prompt") or "text, watermark, logo, blurry, low quality",
                on_screen_text=(str(g.get("on_screen_text") or "")[:300] or None),
                visual_type=visual_type_for(project, order, total_chunks),
                duration_seconds=max(2.0, estimate_duration_seconds(chunk, wpm)),
                transition=transition if transition in VALID_TRANSITIONS else default_transition,
                transition_duration=transition_duration,
                motion_effect=effect if effect in VALID_EFFECTS else default_effect,
                music_suggestion=g.get("music_suggestion"),
                music_mood=g.get("music_mood"),
                sound_effects=list(g.get("sound_effects") or []),
                keywords=list(g.get("keywords") or []),
                status="planned",
            )
            db.add(scene)
            scenes.append(scene)
            order += 1
    db.flush()
    project.estimated_duration_seconds = round(sum(s.duration_seconds for s in scenes), 2)
    record_usage_sync(db, user, UsageKind.LLM_TOKENS, tokens, "tokens", project_id=project.id, job_id=job_id, charge=False)
    return scenes


def renumber_scenes(scenes: list[Scene]) -> None:
    for i, s in enumerate(sorted(scenes, key=lambda x: x.order_index)):
        s.order_index = i


def scene_start_times(scenes: list[Scene]) -> dict[uuid.UUID, float]:
    t = 0.0
    out = {}
    for s in sorted(scenes, key=lambda x: x.order_index):
        out[s.id] = round(t, 3)
        t += float(s.duration_seconds or 0)
    return out


def scenes_for_project(db: Session, project_id: uuid.UUID) -> list[Scene]:
    return list(db.execute(select(Scene).where(Scene.project_id == project_id).order_by(Scene.order_index)).scalars().all())
