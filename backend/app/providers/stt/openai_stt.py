"""OpenAI Whisper transcription adapter with word timestamps."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ProviderTransientError, STTProvider, STTResult, TranscriptSegment, UsageMetrics, WordTiming, provider_retry
from app.providers.http import client, raise_for_provider


class OpenAISTTProvider(STTProvider):
    name = "openai_whisper"
    display_name = "OpenAI Whisper"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_stt_model
        self.base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"word_timestamps": True, "languages": ["*"]}

    @provider_retry
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
        ext = "wav" if "wav" in content_type else "mp3"
        data: dict[str, Any] = {"model": model or self.model, "response_format": "verbose_json"}
        if word_timestamps:
            data["timestamp_granularities[]"] = ["word", "segment"]
        if language:
            data["language"] = language.split("-")[0]
        if prompt:
            data["prompt"] = prompt[:800]
        try:
            with client(600) as c:
                resp = c.post(
                    f"{self.base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": (f"audio.{ext}", audio, content_type)},
                    data=data,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransientError(f"whisper network error: {exc}") from exc
        raise_for_provider(resp, self.name)
        body = resp.json()
        words = [WordTiming(word=w["word"].strip(), start=float(w["start"]), end=float(w["end"])) for w in body.get("words", [])]
        segments = []
        for seg in body.get("segments", []):
            s, e = float(seg["start"]), float(seg["end"])
            segments.append(TranscriptSegment(start=s, end=e, text=seg["text"].strip(), words=[w for w in words if s <= w.start < e]))
        if not segments and words:
            segments = [TranscriptSegment(start=words[0].start, end=words[-1].end, text=body.get("text", ""), words=words)]
        return STTResult(
            text=body.get("text", ""),
            language=body.get("language") or language or "en",
            segments=segments,
            usage=UsageMetrics(provider=self.name, model=data["model"], seconds=float(body.get("duration") or 0), latency_ms=done()),
        )
