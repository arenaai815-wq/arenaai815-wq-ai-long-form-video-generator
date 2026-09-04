"""OpenAI text-to-speech adapter (gpt-4o-mini-tts / tts-1-hd)."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import TTSProvider, TTSResult, UsageMetrics, VoiceInfo, provider_retry
from app.providers.http import request_bytes
from app.providers.mock.tts import plan_timings

VOICES = [
    ("alloy", "Alloy", "neutral"),
    ("ash", "Ash", "male"),
    ("ballad", "Ballad", "male"),
    ("coral", "Coral", "female"),
    ("echo", "Echo", "male"),
    ("fable", "Fable", "neutral"),
    ("nova", "Nova", "female"),
    ("onyx", "Onyx", "male"),
    ("sage", "Sage", "female"),
    ("shimmer", "Shimmer", "female"),
]


class OpenAITTSProvider(TTSProvider):
    name = "openai"
    display_name = "OpenAI Text-to-Speech"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_tts_model
        self.base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"word_timings": False, "speed_range": [0.25, 4.0], "formats": ["mp3", "wav", "opus"], "instructions": True}

    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        return [
            VoiceInfo(id=vid, name=name, language="multilingual", gender=gender, styles=["narration", "conversational"], provider=self.name)
            for vid, name, gender in VOICES
        ]

    @provider_retry
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
        body: dict[str, Any] = {
            "model": model or self.model,
            "input": text,
            "voice": voice_id,
            "speed": max(0.25, min(4.0, speed)),
            "response_format": output_format,
        }
        if style and "gpt-4o" in body["model"]:
            body["instructions"] = f"Speak in a {style} style suitable for a long-form video narration."
        data, ctype = request_bytes(
            "POST",
            f"{self.base_url}/audio/speech",
            provider=self.name,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=300,
        )
        # OpenAI TTS does not return timings; estimate now, refine via STT alignment later.
        timings, est_total = plan_timings(text, speed=speed, style=style)
        duration = _probe_duration(data, output_format) or est_total
        scale = duration / est_total if est_total else 1.0
        for t in timings:
            t.start, t.end = round(t.start * scale, 3), round(t.end * scale, 3)
        return TTSResult(
            data=data,
            content_type=ctype or ("audio/mpeg" if output_format == "mp3" else f"audio/{output_format}"),
            duration_seconds=duration,
            word_timings=timings,
            usage=UsageMetrics(provider=self.name, model=body["model"], characters=len(text), seconds=duration, latency_ms=done()),
        )


def _probe_duration(data: bytes, fmt: str) -> float | None:
    import tempfile

    from app.utils.ffmpeg import media_duration

    try:
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=True) as f:
            f.write(data)
            f.flush()
            d = media_duration(f.name)
            return d or None
    except Exception:
        return None
