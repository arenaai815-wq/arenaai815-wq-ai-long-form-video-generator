"""Prompt templates for every LLM task.

Each user prompt embeds a `<task>{json}</task>` envelope. Real LLMs receive it as extra
structured context; the mock LLM parses it to produce realistic deterministic output.
"""

from __future__ import annotations

import json
from typing import Any

from app.providers.base import LLMMessage

SYSTEM_RESEARCHER = (
    "You are a meticulous research producer for long-form YouTube documentaries and educational videos. "
    "You gather accurate facts, statistics with sources, timelines, key people, controversies and narrative "
    "hooks. You organise research into sections that map to a video structure. You never invent statistics: "
    "when unsure, mark the item as 'needs verification'. Respond only with the JSON schema requested."
)

SYSTEM_SCRIPTWRITER = (
    "You are an award-winning scriptwriter for long-form video (documentaries, video essays, educational "
    "explainers, faceless channels). You write in a natural spoken register for narration: short sentences, "
    "concrete imagery, rhetorical questions, callbacks, and smooth transitions. You match the requested word "
    "count closely because it determines runtime. Never include stage directions, headings or markdown inside "
    "narration text. Respond only with the JSON schema requested."
)

SYSTEM_STORYBOARD = (
    "You are a storyboard artist and cinematographer for AI-generated video. For each narration chunk you "
    "design one visual: a concise visual description, a suggested stock-footage search, a detailed image "
    "generation prompt (subject, composition, lighting, lens, mood, style; no text or logos), a short video "
    "generation prompt with camera motion, optional on-screen text (<= 6 words), a transition and a music "
    "mood. Keep visual continuity across scenes. Respond only with the JSON schema requested."
)


def _envelope(task: str, payload: dict[str, Any]) -> str:
    return f"<task>{json.dumps({'task': task, **payload}, ensure_ascii=False)}</task>"


def research_prompt(
    *,
    topic: str,
    niche: str | None,
    target_audience: str | None,
    language: str,
    tone: str,
    video_format: str,
    target_duration_minutes: int,
    section_count: int,
    depth: str,
    focus: str | None,
    include_sources: bool,
) -> list[LLMMessage]:
    payload = {
        "topic": topic,
        "niche": niche,
        "target_audience": target_audience,
        "language": language,
        "tone": tone,
        "video_format": video_format,
        "target_duration_minutes": target_duration_minutes,
        "section_count": section_count,
        "depth": depth,
        "focus": focus,
        "include_sources": include_sources,
    }
    user = f"""Research the topic below for a {target_duration_minutes}-minute {video_format} video.

Topic: {topic}
Niche: {niche or 'general'}
Audience: {target_audience or 'general audience'}
Language: {language}
Tone: {tone}
Depth: {depth}
{f'Focus on: {focus}' if focus else ''}

Return JSON with this exact shape:
{{
  "summary": "2-4 sentence overview of the topic and the most compelling angle",
  "key_facts": ["..."],
  "statistics": [{{"value": "42%", "context": "what it measures", "source": "publication / dataset"}}],
  "sources": [{{"title": "...", "url": "https://...", "note": "why it matters"}}],
  "suggested_angles": ["..."],
  "keywords": ["..."],
  "sections": [
    {{
      "title": "section title",
      "key_points": ["..."],
      "facts": ["..."],
      "statistics": [{{"value": "...", "context": "...", "source": "..."}}],
      "sources": [{{"title": "...", "url": "...", "note": "..."}}],
      "narrative_hooks": ["an anecdote, question or surprising detail that can open this section"]
    }}
  ]
}}
Produce exactly {section_count} sections ordered as a narrative arc.
{_envelope('research', payload)}"""
    return [LLMMessage(role="system", content=SYSTEM_RESEARCHER), LLMMessage(role="user", content=user)]


def script_outline_prompt(
    *,
    topic: str,
    title_hint: str | None,
    tone: str,
    language: str,
    video_format: str,
    target_audience: str | None,
    target_duration_minutes: int,
    words_per_minute: int,
    research_summary: str | None,
    research_sections: list[dict[str, Any]],
    instructions: str | None,
) -> list[LLMMessage]:
    # Budget ~90% of the runtime for spoken words; the rest is pauses, intro/outro and transitions.
    total_words = int(target_duration_minutes * words_per_minute * 0.9)
    compact_sections = [
        {"title": s.get("title"), "key_points": (s.get("key_points") or [])[:5]} for s in research_sections
    ]
    payload = {
        "topic": topic,
        "target_duration_minutes": target_duration_minutes,
        "words_per_minute": words_per_minute,
        "research_sections": compact_sections,
        "tone": tone,
    }
    user = f"""Plan the structure of a {target_duration_minutes}-minute {video_format} video (~{total_words} words at {words_per_minute} wpm).

Topic: {topic}
Working title: {title_hint or 'none'}
Audience: {target_audience or 'general audience'}
Tone: {tone} | Language: {language}
Research summary: {research_summary or 'n/a'}
Research sections: {json.dumps(compact_sections, ensure_ascii=False)}
{f'Extra instructions: {instructions}' if instructions else ''}

Return JSON:
{{
  "title": "final video title",
  "hook": "one or two sentence cold-open hook",
  "sections": [
    {{"kind": "hook|intro|body|transition|story|conclusion|cta", "heading": "...", "target_words": 123, "talking_points": ["..."]}}
  ]
}}
Rules: start with a hook and intro, end with conclusion and a short cta; body sections should sum to the
remaining word budget; target_words across all sections must total about {total_words}.
{_envelope('script_outline', payload)}"""
    return [LLMMessage(role="system", content=SYSTEM_SCRIPTWRITER), LLMMessage(role="user", content=user)]


def script_section_prompt(
    *,
    topic: str,
    title: str | None,
    tone: str,
    language: str,
    target_audience: str | None,
    kind: str,
    heading: str,
    target_words: int,
    talking_points: list[str],
    facts: list[str],
    previous_summary: str | None,
    next_heading: str | None,
    instructions: str | None,
) -> list[LLMMessage]:
    payload = {
        "topic": topic,
        "heading": heading,
        "kind": kind,
        "target_words": target_words,
        "talking_points": talking_points,
        "facts": facts[:6],
        "tone": tone,
        "target_audience": target_audience,
    }
    user = f"""Write the narration for ONE section of the video "{title or topic}".

Section kind: {kind}
Heading: {heading}
Target length: {target_words} words (±10%)
Talking points: {json.dumps(talking_points, ensure_ascii=False)}
Facts to weave in: {json.dumps(facts[:6], ensure_ascii=False)}
Previously covered: {previous_summary or 'this is the opening'}
Next section: {next_heading or 'this is the end of the video'}
Tone: {tone} | Language: {language} | Audience: {target_audience or 'general'}
{f'Extra instructions: {instructions}' if instructions else ''}

Return JSON:
{{"heading": "...", "content": "plain narration text only", "summary": "one sentence", "on_screen_text_ideas": ["..."]}}
{_envelope('script_section', payload)}"""
    return [LLMMessage(role="system", content=SYSTEM_SCRIPTWRITER), LLMMessage(role="user", content=user)]


def scene_breakdown_prompt(
    *,
    topic: str,
    visual_style: str,
    aspect_ratio: str,
    heading: str,
    chunks: list[str],
    previous_visual: str | None,
) -> list[LLMMessage]:
    payload = {"topic": topic, "visual_style": visual_style, "heading": heading, "chunks": chunks}
    user = f"""Design one scene per narration chunk for the section "{heading}" of a video about "{topic}".
Visual style: {visual_style}. Aspect ratio: {aspect_ratio}.
Previous scene visual (for continuity): {previous_visual or 'none'}

Narration chunks (keep text EXACTLY as given, in order):
{json.dumps(chunks, ensure_ascii=False, indent=1)}

Return JSON:
{{"scenes": [{{
  "title": "...",
  "narration": "<exact chunk text>",
  "visual_description": "...",
  "suggested_footage": "...",
  "image_prompt": "...",
  "video_prompt": "...",
  "negative_prompt": "...",
  "on_screen_text": "" ,
  "keywords": ["..."],
  "transition": "fade|dissolve|slideleft|wipeleft|fadeblack|smoothleft|none",
  "motion_effect": "ken_burns|zoom_in|zoom_out|pan_left|pan_right|none",
  "music_suggestion": "...",
  "music_mood": "inspiring|tense|calm|uplifting|mysterious|reflective|energetic",
  "sound_effects": ["..."]
}}]}}
{_envelope('scene_breakdown', payload)}"""
    return [LLMMessage(role="system", content=SYSTEM_STORYBOARD), LLMMessage(role="user", content=user)]


def title_ideas_prompt(*, topic: str, target_duration_minutes: int, tone: str) -> list[LLMMessage]:
    payload = {"topic": topic, "target_duration_minutes": target_duration_minutes, "tone": tone}
    user = f"""Suggest 5 click-worthy but honest YouTube titles for a {target_duration_minutes}-minute video about "{topic}" ({tone} tone).
Return JSON: {{"titles": ["..."]}}
{_envelope('title_ideas', payload)}"""
    return [LLMMessage(role="system", content=SYSTEM_SCRIPTWRITER), LLMMessage(role="user", content=user)]
