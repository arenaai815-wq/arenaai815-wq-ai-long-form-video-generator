"""Mock speech-to-text.

Without a real STT model we cannot recognise audio content, so the mock derives
timestamps from the audio duration and an optional `prompt` (the known narration text).
This mirrors how a production deployment can use *forced alignment* with the script,
which is more accurate than free transcription for TTS-generated narration.
"""

from __future__ import annotations

import io
import wave
from typing import Any

from app.providers.base import STTProvider, STTResult, TranscriptSegment, UsageMetrics, WordTiming
from app.providers.mock.tts import plan_timings
from app.utils.text import split_sentences


def _duration_of(audio: bytes, content_type: str) -> float | None:
    if "wav" in content_type:
        try:
            with wave.open(io.BytesIO(audio), "rb") as wf:
                return wf.getnframes() / float(wf.getframerate())
        except Exception:
            return None
    return None


class MockSTTProvider(STTProvider):
    name = "mock"
    display_name = "Mock Speech-to-Text (development)"
    is_mock = True
    model = "mock-stt-v1"

    def capabilities(self) -> dict[str, Any]:
        return {"word_timestamps": True, "languages": ["*"], "alignment": True}

    def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str = "audio/mpeg",
        language: str | None = None,
        prompt: str | None = None,
        word_timestamps: bool = True,
        model: str | None = None,
    ) -> STTResult:
        done = self._timer()
        text = (prompt or "").strip()
        duration = _duration_of(audio, content_type) or 0.0
        if not text:
            return STTResult(
                text="",
                language=language or "en",
                segments=[],
                usage=UsageMetrics(provider=self.name, model=self.model, seconds=duration, latency_ms=done()),
            )
        timings, planned_total = plan_timings(text)
        # Stretch planned timings to fit the actual audio duration if known
        scale = (duration / planned_total) if duration and planned_total else 1.0
        words = [WordTiming(word=w.word, start=round(w.start * scale, 3), end=round(w.end * scale, 3)) for w in timings]

        segments: list[TranscriptSegment] = []
        cursor = 0
        for sentence in split_sentences(text):
            n = len([t for t in sentence.split() if any(ch.isalnum() for ch in t)])
            seg_words = words[cursor : cursor + n]
            cursor += n
            if not seg_words:
                continue
            segments.append(
                TranscriptSegment(start=seg_words[0].start, end=seg_words[-1].end, text=sentence, words=seg_words)
            )
        return STTResult(
            text=text,
            language=language or "en",
            segments=segments,
            usage=UsageMetrics(provider=self.name, model=self.model, seconds=duration, latency_ms=done()),
        )
