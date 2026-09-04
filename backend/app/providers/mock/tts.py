"""Mock TTS provider.

Synthesises a speech-like audio track (band-limited noise bursts shaped per syllable with
pauses at punctuation) whose duration matches the estimated narration time, plus
word-level timings. Captions, timeline and rendering behave exactly as they will with a
real provider - only the audible content is a placeholder.
"""

from __future__ import annotations

import io
import math
import random
import re
import struct
import wave
from typing import Any

import numpy as np

from app.providers.base import TTSProvider, TTSResult, UsageMetrics, VoiceInfo, WordTiming
from app.utils.text import estimate_duration_seconds, wpm_for_tone

SAMPLE_RATE = 24000

MOCK_VOICES = [
    VoiceInfo(id="mock-aria", name="Aria", language="en", gender="female", accent="American", styles=["narration", "documentary", "conversational"], provider="mock"),
    VoiceInfo(id="mock-noah", name="Noah", language="en", gender="male", accent="American", styles=["narration", "energetic", "commentary"], provider="mock"),
    VoiceInfo(id="mock-oliver", name="Oliver", language="en-GB", gender="male", accent="British", styles=["documentary", "calm"], provider="mock"),
    VoiceInfo(id="mock-amara", name="Amara", language="en-NG", gender="female", accent="Nigerian", styles=["storytelling", "warm"], provider="mock"),
    VoiceInfo(id="mock-lucia", name="Lucía", language="es", gender="female", accent="Castilian", styles=["narration"], provider="mock"),
    VoiceInfo(id="mock-jean", name="Jean", language="fr", gender="male", accent="Parisian", styles=["narration"], provider="mock"),
    VoiceInfo(id="mock-hana", name="Hana", language="ja", gender="female", accent="Tokyo", styles=["calm"], provider="mock"),
    VoiceInfo(id="mock-lena", name="Lena", language="de", gender="female", accent="Standard", styles=["educational"], provider="mock"),
]

_TOKEN_RE = re.compile(r"[A-Za-z0-9À-ÿ'’\-]+|[.,;:!?]")


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def plan_timings(text: str, speed: float = 1.0, style: str | None = None) -> tuple[list[WordTiming], float]:
    """Compute deterministic word timings at ~wpm(style) adjusted by speed."""
    wpm = wpm_for_tone(style) * max(0.5, min(2.0, speed))
    base_word = 60.0 / wpm  # seconds per average (1.5 syllable) word, all-in
    # Reserve part of the per-word budget for the inter-word gap and punctuation pauses so
    # the *effective* pace of the generated audio matches `wpm` (calibrated on prose).
    per_syllable = (base_word * 0.80 - 0.045) / 1.5
    t = 0.15  # lead-in silence
    timings: list[WordTiming] = []
    for tok in _TOKEN_RE.findall(text or ""):
        if tok in ".!?":
            t += 0.42 / speed
        elif tok in ",;:":
            t += 0.2 / speed
        else:
            dur = per_syllable * _syllables(tok) + 0.02 * len(tok) / 6
            timings.append(WordTiming(word=tok, start=round(t, 3), end=round(t + dur, 3)))
            t += dur + 0.045
    total = t + 0.25
    # Calibrate so the mock audio length equals the platform's narration estimate for this
    # pace (the same estimate the script editor displays), keeping relative word timings.
    est = estimate_duration_seconds(text or "", int(wpm)) + 0.4
    if timings and total > 0 and est > 0:
        k = est / total
        timings = [WordTiming(word=w.word, start=round(w.start * k, 3), end=round(w.end * k, 3)) for w in timings]
        total = est
    return timings, round(total, 3)


def synthesize_wave(timings: list[WordTiming], total: float, *, voice_id: str, sample_rate: int = SAMPLE_RATE) -> bytes:
    rng = random.Random(voice_id)
    n = int(total * sample_rate) + 1
    audio = np.zeros(n, dtype=np.float32)
    # Voice character: base pitch and formant emphasis vary per voice id
    base_f0 = rng.uniform(95, 125) if "noah" in voice_id or "oliver" in voice_id or "jean" in voice_id else rng.uniform(170, 220)
    t_axis = np.arange(n) / sample_rate
    for wt in timings:
        s, e = int(wt.start * sample_rate), int(wt.end * sample_rate)
        if e <= s:
            continue
        seg_t = t_axis[s:e] - wt.start
        length = e - s
        # Intonation contour + vibrato
        f0 = base_f0 * (1 + 0.08 * math.sin(wt.start * 1.7)) * (1 + 0.02 * np.sin(2 * np.pi * 5 * seg_t))
        phase = 2 * np.pi * np.cumsum(f0) / sample_rate
        harmonics = sum((1.0 / (k**1.2)) * np.sin(k * phase) for k in range(1, 7))
        # Consonant-like noise burst at word start
        noise = np.random.default_rng(int(wt.start * 1000)).normal(0, 0.35, length) * np.exp(-seg_t * 40)
        env = np.sin(np.pi * np.linspace(0, 1, length)) ** 0.6  # syllable envelope
        seg = (harmonics * 0.28 + noise * 0.4) * env
        audio[s:e] += seg.astype(np.float32)
    # Gentle low-pass via moving average to soften buzz
    kernel = np.ones(24, dtype=np.float32) / 24
    audio = np.convolve(audio, kernel, mode="same")
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak * 0.7 * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class MockTTSProvider(TTSProvider):
    name = "mock"
    display_name = "Mock Text-to-Speech (development)"
    is_mock = True
    model = "mock-tts-v1"

    def capabilities(self) -> dict[str, Any]:
        return {"word_timings": True, "ssml": False, "speed_range": [0.5, 2.0], "formats": ["wav"], "languages": sorted({v.language for v in MOCK_VOICES})}

    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        if not language:
            return list(MOCK_VOICES)
        lang = language.lower()
        return [v for v in MOCK_VOICES if v.language.lower().startswith(lang.split("-")[0])]

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        language: str = "en",
        speed: float = 1.0,
        style: str | None = None,
        output_format: str = "mp3",
        model: str | None = None,
    ) -> TTSResult:
        done = self._timer()
        timings, total = plan_timings(text, speed=speed, style=style)
        data = synthesize_wave(timings, total, voice_id=voice_id)
        return TTSResult(
            data=data,
            content_type="audio/wav",
            duration_seconds=total,
            sample_rate=SAMPLE_RATE,
            word_timings=timings,
            usage=UsageMetrics(provider=self.name, model=self.model, characters=len(text), seconds=total, latency_ms=done()),
        )


def wav_duration(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        # naive fallback for raw pcm16 mono 24k
        return len(data) / (2 * SAMPLE_RATE)


__all__ = ["MockTTSProvider", "plan_timings", "synthesize_wave", "wav_duration", "struct"]
