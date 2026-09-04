"""Mock LLM.

It recognises the structured prompts emitted by `app.services.prompts` (each carries a
`"task": "<name>"` marker in the user message) and returns realistic, well-formed JSON
for research, scripts, sections and scene breakdowns. For unknown prompts it returns a
generic paragraph. Output is deterministic for a given input so tests are stable.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any

from app.providers.base import LLMMessage, LLMProvider, LLMResult, UsageMetrics
from app.utils.text import word_count


def _subject(topic: str) -> str:
    """Turn a long topic sentence into a short noun phrase usable mid-sentence."""
    t = re.sub(r"^(how|why|what|when|where|the story of|the history of)\s+", "", topic.strip(), flags=re.I)
    words = t.split()
    if len(words) > 7:
        t = " ".join(words[:7]).rstrip(",;:")
    return t[0].lower() + t[1:] if t and not t.isupper() and not t[:2].isupper() else t


def _seed_from(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _extract_task(messages: list[LLMMessage]) -> tuple[str, dict[str, Any]]:
    """Find the JSON task envelope in the last user message."""
    for m in reversed(messages):
        if m.role != "user":
            continue
        match = re.search(r"<task>(.*?)</task>", m.content, re.S)
        if match:
            try:
                payload = json.loads(match.group(1))
                return str(payload.get("task", "")), payload
            except json.JSONDecodeError:
                pass
    return "", {}


class MockLLMProvider(LLMProvider):
    name = "mock"
    display_name = "Mock LLM (development)"
    is_mock = True
    model = "mock-llm-v1"

    def capabilities(self) -> dict[str, Any]:
        return {"json_mode": True, "streaming": False, "max_context": 128000}

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResult:
        done = self._timer()
        task, payload = _extract_task(messages)
        rng = random.Random(_seed_from(json.dumps(payload, sort_keys=True) if payload else messages[-1].content))

        handlers = {
            "research": self._research,
            "script_outline": self._script_outline,
            "script_section": self._script_section,
            "scene_breakdown": self._scene_breakdown,
            "title_ideas": self._title_ideas,
        }
        if task in handlers:
            data = handlers[task](payload, rng)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            parsed: Any = data
        else:
            prompt = messages[-1].content
            text = self._generic(prompt, rng)
            parsed = None
            if json_mode:
                text = json.dumps({"text": text})
                parsed = {"text": text}

        input_tokens = sum(word_count(m.content) for m in messages) * 4 // 3
        output_tokens = word_count(text) * 4 // 3
        return LLMResult(
            text=text,
            parsed=parsed if json_mode else None,
            usage=UsageMetrics(
                provider=self.name,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=done(),
            ),
        )

    # ------------------------------------------------------------------ tasks

    def _research(self, p: dict, rng: random.Random) -> dict:
        topic = p.get("topic", "the topic")
        audience = p.get("target_audience") or "a general audience"
        n_sections = int(p.get("section_count") or 6)
        angles = [
            f"The untold origin story of {topic}",
            f"Why {topic} matters more than ever in {2026}",
            f"The biggest misconceptions about {topic}",
            f"How {topic} actually works, explained simply",
            f"What experts predict next for {topic}",
        ]
        section_titles = [
            "Origins and historical context",
            "How it works: the core mechanics",
            "Key figures, turning points and milestones",
            "Impact on society, economy and culture",
            "Controversies, risks and open questions",
            "The road ahead: trends and predictions",
            "Lessons and takeaways",
            "Case studies and real-world examples",
        ]
        sections = []
        for i in range(n_sections):
            title = section_titles[i % len(section_titles)]
            sections.append(
                {
                    "title": title,
                    "key_points": [
                        f"{title.split(':')[0]} of {topic}: point {j + 1} tailored for {audience}."
                        for j in range(4)
                    ],
                    "facts": [
                        f"Fact {j + 1}: a verifiable detail about {topic} relating to {title.lower()}."
                        for j in range(3)
                    ],
                    "statistics": [
                        {
                            "value": f"{rng.randint(12, 94)}%",
                            "context": f"share of surveyed people who associate {topic} with {title.lower()}",
                            "source": "Industry survey (mock data)",
                        },
                        {
                            "value": f"${rng.randint(2, 480)}B",
                            "context": f"estimated market/economic footprint linked to {topic}",
                            "source": "Analyst estimate (mock data)",
                        },
                    ],
                    "sources": [
                        {
                            "title": f"{title} - encyclopedia overview",
                            "url": f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}",
                            "note": "Background reading",
                        },
                        {
                            "title": f"Research paper on {topic}",
                            "url": "https://scholar.google.com/",
                            "note": "Primary source (replace with a real citation)",
                        },
                    ],
                    "narrative_hooks": [
                        f"Imagine a world where {topic} never existed.",
                        f"Nobody expected {topic} to change {title.split(' ')[0].lower()} the way it did.",
                    ],
                }
            )
        return {
            "summary": (
                f"{topic} is a rich subject for {audience}. This research pack organises the history, "
                f"mechanics, key people, impact and future of {topic} into {n_sections} sections that map "
                f"directly onto a long-form video structure. Replace the mock statistics with verified figures "
                f"before publishing."
            ),
            "key_facts": [f"Key fact {i + 1} about {topic} that anchors the narrative." for i in range(8)],
            "statistics": [s for sec in sections for s in sec["statistics"]][:8],
            "sources": [s for sec in sections for s in sec["sources"]][:10],
            "suggested_angles": angles,
            "keywords": [w.lower() for w in re.findall(r"[A-Za-z]{4,}", topic)][:6] + ["explained", "history", "documentary"],
            "sections": sections,
        }

    def _script_outline(self, p: dict, rng: random.Random) -> dict:
        topic = p.get("topic", "the topic")
        minutes = int(p.get("target_duration_minutes") or 10)
        wpm = int(p.get("words_per_minute") or 150)
        research_sections = p.get("research_sections") or []
        # ~10% of runtime goes to sentence/clause pauses, intro/outro cards and transitions.
        total_words = max(120, int(minutes * wpm * 0.9))
        # Scale structure with length: a 1-minute short gets 1-2 chapters, an hour gets 12.
        body_count = max(1, min(12, minutes // 3 + (2 if minutes >= 3 else 1)))
        short = minutes <= 2
        hook_words = max(15 if short else 25, int(total_words * 0.05))
        intro_words = max(20 if short else 30, int(total_words * 0.08))
        concl_words = max(20 if short else 30, int(total_words * 0.08))
        cta_words = 45 if minutes >= 5 else 15
        body_words = max(40, (total_words - hook_words - intro_words - concl_words - cta_words) // body_count)

        sections: list[dict] = [
            {"kind": "hook", "heading": "Cold open", "target_words": hook_words, "talking_points": [f"A provocative question about {topic}", "A surprising statistic", "Promise of what the viewer will learn"]},
            {"kind": "intro", "heading": "Introduction", "target_words": intro_words, "talking_points": [f"Why {topic} matters", "Roadmap of the video", "Set expectations and tone"]},
        ]
        for i in range(body_count):
            src = research_sections[i % len(research_sections)] if research_sections else {}
            heading = src.get("title") or f"Chapter {i + 1}: exploring {topic}"
            sections.append(
                {
                    "kind": "body",
                    "heading": heading,
                    "target_words": body_words,
                    "talking_points": (src.get("key_points") or [f"Point {j + 1} about {heading}" for j in range(3)])[:4],
                }
            )
            if minutes >= 5 and i < body_count - 1 and rng.random() < 0.4:
                sections.append({"kind": "transition", "heading": f"Bridge to chapter {i + 2}", "target_words": 40, "talking_points": ["Recap", "Tease next chapter"]})
        sections.append({"kind": "conclusion", "heading": "Conclusion", "target_words": concl_words, "talking_points": ["Synthesize the key insights", "Return to the opening question", "Leave a lasting thought"]})
        sections.append({"kind": "cta", "heading": "Outro & call to action", "target_words": cta_words, "talking_points": ["Subscribe / like", "Next video tease"]})
        return {
            "title": f"{topic}: The Complete Story",
            "hook": f"What if everything you thought you knew about {topic} was only half the story?",
            "sections": sections,
        }

    def _script_section(self, p: dict, rng: random.Random) -> dict:
        topic = _subject(p.get("topic", "the topic"))
        subject = topic
        heading = p.get("heading", "Section")
        kind = p.get("kind", "body")
        target = int(p.get("target_words") or 200)
        tone = p.get("tone", "engaging")
        points = p.get("talking_points") or [f"an important aspect of {topic}"]
        facts = p.get("facts") or []
        audience = p.get("target_audience") or "viewers"

        openers = {
            "hook": [
                f"Picture this. It is a quiet morning, and nobody suspects that {topic} is about to change everything.",
                f"Here is a number that should stop you in your tracks: nearly half of all people misunderstand {topic}.",
            ],
            "intro": [
                f"Welcome. Over the next few minutes we are going on a journey through {topic} — where it came from, how it works, and why it matters to {audience}.",
            ],
            "body": [
                f"Let's start with {points[0].lower() if points else topic}.",
                f"To understand {heading.lower()}, we first need to look closely at {topic}.",
                f"This is where the story of {topic} takes an unexpected turn.",
            ],
            "transition": [
                f"So far we have seen how {topic} took shape. But that is only the beginning.",
            ],
            "conclusion": [
                f"So where does this leave us? {topic} is not just a subject to study — it is a lens for understanding the world around us.",
            ],
            "cta": [
                "If this video gave you a new perspective, consider subscribing — there is a lot more where this came from.",
            ],
        }
        fillers = [
            "Consider what that really means in practice.",
            "The details here are where the story gets interesting.",
            "It is easy to overlook, but this detail matters more than almost anything else.",
            "Experts have debated this for years, and the evidence points in one direction.",
            "The implications ripple outward in ways few people anticipated.",
            "Take a moment to think about how this connects to your own experience.",
            "This is the kind of nuance that separates a surface-level take from real understanding.",
            "And yet, the most fascinating part is still to come.",
        ]

        # Candidate sentences in priority order; we stop as soon as the target is met so
        # short scripts (1-2 minute videos) do not balloon past their duration budget.
        candidates: list[str] = []
        for pt in points:
            candidates.append(f"{pt[0].upper() + pt[1:]}." if not pt.endswith(".") else pt)
            candidates.append(f"For {audience}, this shapes how the subject is experienced day to day.")
        for f in facts:
            candidates.append(f if f.endswith(".") else f + ".")
        sentences: list[str] = [rng.choice(openers.get(kind, openers["body"]))]
        i = 0
        while word_count(" ".join(sentences)) < target and i < 400:
            sentences.append(candidates[i] if i < len(candidates) else rng.choice(fillers))
            i += 1
        if kind in ("body", "story") and word_count(" ".join(sentences)) < target * 1.05:
            sentences.append(f"Which brings us to the next chapter in the story of {subject}.")
        # Trim back to within ~10% of the word budget so the narration duration tracks the
        # requested video length (an opener + one point is always kept).
        while len(sentences) > 2 and word_count(" ".join(sentences)) > target * 1.05:
            sentences.pop()
        content = " ".join(sentences)
        return {
            "heading": heading,
            "content": content,
            "summary": f"{heading}: covers {', '.join(points[:2])} in a {tone} tone.",
            "on_screen_text_ideas": [heading, points[0][:40] if points else topic],
        }

    def _scene_breakdown(self, p: dict, rng: random.Random) -> dict:
        topic = p.get("topic", "the topic")
        style = p.get("visual_style", "cinematic")
        heading = p.get("heading", "")
        chunks: list[str] = p.get("chunks") or []
        moods = ["inspiring", "tense", "calm", "uplifting", "mysterious", "reflective", "energetic"]
        shots = ["wide establishing shot", "slow push-in", "aerial drone shot", "close-up detail", "archival photograph", "macro shot", "time-lapse", "tracking shot"]
        transitions = ["fade", "dissolve", "slideleft", "wipeleft", "fadeblack", "smoothleft"]
        effects = ["ken_burns", "zoom_in", "zoom_out", "pan_left", "pan_right"]
        scenes = []
        for i, chunk in enumerate(chunks):
            subject = re.sub(r"[^A-Za-z ]", "", chunk).strip().split(".")[0][:80] or topic
            shot = rng.choice(shots)
            mood = rng.choice(moods)
            scenes.append(
                {
                    "title": f"{heading or 'Scene'} — part {i + 1}" if heading else f"Scene {i + 1}",
                    "narration": chunk,
                    "visual_description": f"A {shot} illustrating '{subject}'. {style.capitalize()} lighting, {mood} mood, high detail, cohesive colour grade.",
                    "suggested_footage": f"Stock: {shot} related to {topic}; alternatives: archival stills, infographic overlay.",
                    "image_prompt": f"{style} {shot} of {subject}, related to {topic}, {mood} atmosphere, dramatic natural lighting, ultra detailed, 8k, photorealistic, 16:9",
                    "video_prompt": f"{shot}, {subject}, {topic}, {style}, {mood}, smooth camera motion, cinematic, 4k",
                    "negative_prompt": "text, watermark, logo, blurry, low quality, distorted hands, extra limbs",
                    "on_screen_text": subject[:48] if i % 3 == 0 else "",
                    "keywords": [w.lower() for w in re.findall(r"[A-Za-z]{5,}", subject)][:5],
                    "transition": rng.choice(transitions),
                    "motion_effect": rng.choice(effects),
                    "music_suggestion": f"{mood} ambient score, soft strings and piano, ~{rng.randint(70, 110)} BPM",
                    "music_mood": mood,
                    "sound_effects": rng.sample(["whoosh", "soft riser", "paper rustle", "subtle impact", "ambient room tone", "typing"], k=rng.randint(0, 2)),
                }
            )
        return {"scenes": scenes}

    def _title_ideas(self, p: dict, rng: random.Random) -> dict:
        topic = p.get("topic", "the topic")
        return {
            "titles": [
                f"The Untold Story of {topic}",
                f"{topic}, Explained in {p.get('target_duration_minutes', 10)} Minutes",
                f"Why {topic} Changed Everything",
                f"The Truth About {topic}",
                f"{topic}: A Documentary",
            ]
        }

    def _generic(self, prompt: str, rng: random.Random) -> str:
        return (
            "This is a development response from the mock LLM provider. Configure LLM_PROVIDER=openai "
            "(or anthropic / openai_compatible) with an API key to get real completions. "
            f"Prompt preview: {prompt[:160]!r}"
        )
