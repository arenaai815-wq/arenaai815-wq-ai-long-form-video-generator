"""ElevenLabs adapter using the `with-timestamps` endpoint for real word timings."""

from __future__ import annotations

import base64
from typing import Any

from app.core.config import settings
from app.providers.base import TTSProvider, TTSResult, UsageMetrics, VoiceInfo, WordTiming, provider_retry
from app.providers.http import request_json
from app.providers.tts.openai_tts import _probe_duration

API = "https://api.elevenlabs.io/v1"


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"
    display_name = "ElevenLabs"

    def __init__(self, *, api_key: str | None = None, model_id: str | None = None):
        self.api_key = api_key or settings.elevenlabs_api_key
        self.model = model_id or settings.elevenlabs_model_id

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"word_timings": True, "speed_range": [0.7, 1.2], "formats": ["mp3"], "voice_cloning": True}

    def list_voices(self, language: str | None = None) -> list[VoiceInfo]:
        data = request_json("GET", f"{API}/voices", provider=self.name, headers={"xi-api-key": self.api_key or ""})
        voices = []
        for v in data.get("voices", []):
            labels = v.get("labels") or {}
            voices.append(
                VoiceInfo(
                    id=v["voice_id"],
                    name=v.get("name", v["voice_id"]),
                    language=labels.get("language", "multilingual"),
                    gender=labels.get("gender"),
                    accent=labels.get("accent"),
                    styles=[labels.get("use_case")] if labels.get("use_case") else [],
                    preview_url=v.get("preview_url"),
                    provider=self.name,
                    is_premium=v.get("category") == "professional",
                )
            )
        return voices

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
        data = request_json(
            "POST",
            f"{API}/text-to-speech/{voice_id}/with-timestamps",
            provider=self.name,
            headers={"xi-api-key": self.api_key or "", "Content-Type": "application/json"},
            params={"output_format": "mp3_44100_128"},
            json={
                "text": text,
                "model_id": model or self.model,
                "language_code": language.split("-")[0] if (model or self.model).startswith("eleven_turbo") or "flash" in (model or self.model) else None,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3 if style else 0.0, "speed": max(0.7, min(1.2, speed))},
            },
            timeout=300,
        )
        audio = base64.b64decode(data["audio_base64"])
        timings = _chars_to_words(data.get("alignment") or data.get("normalized_alignment") or {})
        duration = _probe_duration(audio, "mp3") or (timings[-1].end + 0.2 if timings else 0.0)
        return TTSResult(
            data=audio,
            content_type="audio/mpeg",
            duration_seconds=duration,
            sample_rate=44100,
            word_timings=timings,
            usage=UsageMetrics(provider=self.name, model=model or self.model, characters=len(text), seconds=duration, latency_ms=done()),
        )


def _chars_to_words(alignment: dict[str, Any]) -> list[WordTiming]:
    chars: list[str] = alignment.get("characters") or []
    starts: list[float] = alignment.get("character_start_times_seconds") or []
    ends: list[float] = alignment.get("character_end_times_seconds") or []
    words: list[WordTiming] = []
    buf, w_start, w_end = "", None, None
    for ch, s, e in zip(chars, starts, ends, strict=False):
        if ch.isspace():
            if buf:
                words.append(WordTiming(word=buf, start=round(w_start or 0, 3), end=round(w_end or 0, 3)))
            buf, w_start, w_end = "", None, None
            continue
        if w_start is None:
            w_start = s
        w_end = e
        buf += ch
    if buf:
        words.append(WordTiming(word=buf, start=round(w_start or 0, 3), end=round(w_end or 0, 3)))
    return words
