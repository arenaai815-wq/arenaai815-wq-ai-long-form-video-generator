"""Duration estimation, chunking and the mock LLM/TTS calibration that the pipeline relies on."""
from __future__ import annotations

import random

from app.providers.mock.llm import MockLLMProvider
from app.providers.mock.tts import plan_timings
from app.services.scene_service import chunk_narration
from app.utils.text import estimate_duration_seconds, word_count, wpm_for_tone

TOPIC = "How the Sahara desert changed from green savanna to the largest hot desert"


def test_word_count_and_duration_estimate_scale_linearly():
    text = " ".join(["word"] * 150) + "."
    assert word_count(text) == 150
    est = estimate_duration_seconds(text, 150)
    assert 60 <= est <= 61  # 150 words at 150 wpm + one sentence pause


def test_wpm_for_tone_falls_back_to_default():
    assert wpm_for_tone("documentary") == 140
    assert wpm_for_tone(None) == 150
    assert wpm_for_tone("unknown-tone") == 150


def test_chunk_narration_produces_scene_sized_chunks_without_tiny_scenes():
    text = "Picture this. " + " ".join(f"Sentence number {i} carries some meaningful narration for the viewer." for i in range(40))
    chunks = chunk_narration(text, target_seconds=9, wpm=150)
    assert len(chunks) >= 5
    assert " ".join(chunks).split() == text.split()  # nothing lost or duplicated
    assert all(len(c.split()) >= 6 for c in chunks)  # tiny fragments were merged
    assert max(len(c.split()) for c in chunks) <= 40


def test_mock_script_hits_duration_budget_across_lengths():
    llm = MockLLMProvider()
    for minutes in (1, 5, 20):
        outline = llm._script_outline({"topic": TOPIC, "target_duration_minutes": minutes, "words_per_minute": 150, "research_sections": []}, random.Random(1))
        kinds = [s["kind"] for s in outline["sections"]]
        assert kinds[0] == "hook" and kinds[1] == "intro" and kinds[-2:] == ["conclusion", "cta"]
        narration = 0.0
        for sec in outline["sections"]:
            written = llm._script_section({**sec, "topic": TOPIC, "tone": "documentary", "facts": ["In 1969 four computers were connected."]}, random.Random(2))
            narration += plan_timings(written["content"], style="narration")[1]
        # narration should land within ~30% of the requested runtime (short videos have fixed overheads)
        assert 0.7 * minutes * 60 <= narration <= 1.35 * minutes * 60, (minutes, narration)


def test_mock_tts_timings_are_monotonic_and_match_estimate():
    text = "Hello world, this is a narration test. It has two sentences!"
    timings, total = plan_timings(text, speed=1.0, style="narration")
    assert [t.word for t in timings] == ["Hello", "world", "this", "is", "a", "narration", "test", "It", "has", "two", "sentences"]
    assert all(a.end <= b.start for a, b in zip(timings, timings[1:], strict=False))
    assert timings[-1].end <= total
    faster = plan_timings(text, speed=1.5, style="narration")[1]
    assert faster < total


def test_mock_scene_breakdown_builds_prompts_and_on_screen_text():
    llm = MockLLMProvider()
    out = llm._scene_breakdown(
        {"topic": TOPIC, "visual_style": "cinematic documentary", "heading": "Cold open", "chunks": ["Picture this. The Sahara desert is about to change.", "Ten thousand years ago the Sahara received far more rainfall than today."]},
        random.Random(3),
    )
    scenes = out["scenes"]
    assert len(scenes) == 2
    assert scenes[0]["on_screen_text"] == "Cold open"
    for s in scenes:
        assert s["narration"]
        assert "Sahara" in s["image_prompt"]
        assert s["transition"] and s["motion_effect"] and s["music_mood"]
        assert 0 <= len(s["sound_effects"]) <= 2
