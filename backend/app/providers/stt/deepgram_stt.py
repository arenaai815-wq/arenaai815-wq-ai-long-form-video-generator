"""Deepgram Nova transcription adapter."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ProviderTransientError, STTProvider, STTResult, TranscriptSegment, UsageMetrics, WordTiming, provider_retry
from app.providers.http import client, raise_for_provider


class DeepgramSTTProvider(STTProvider):
    name = "deepgram"
    display_name = "Deepgram Nova"

    def __init__(self, *, api_key: str | None = None, model: str = "nova-2"):
        self.api_key = api_key or settings.deepgram_api_key
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"word_timestamps": True, "languages": ["*"], "diarization": True}

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
        params: dict[str, Any] = {"model": model or self.model, "smart_format": "true", "punctuate": "true", "utterances": "true"}
        if language:
            params["language"] = language
        try:
            with client(600) as c:
                resp = c.post(
                    "https://api.deepgram.com/v1/listen",
                    params=params,
                    headers={"Authorization": f"Token {self.api_key}", "Content-Type": content_type},
                    content=audio,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransientError(f"deepgram network error: {exc}") from exc
        raise_for_provider(resp, self.name)
        body = resp.json()
        alt = body["results"]["channels"][0]["alternatives"][0]
        words = [WordTiming(word=w.get("punctuated_word") or w["word"], start=float(w["start"]), end=float(w["end"])) for w in alt.get("words", [])]
        segments = []
        for utt in body["results"].get("utterances", []):
            s, e = float(utt["start"]), float(utt["end"])
            segments.append(TranscriptSegment(start=s, end=e, text=utt["transcript"], words=[w for w in words if s <= w.start <= e]))
        if not segments and words:
            segments = [TranscriptSegment(start=words[0].start, end=words[-1].end, text=alt.get("transcript", ""), words=words)]
        return STTResult(
            text=alt.get("transcript", ""),
            language=language or body.get("metadata", {}).get("detected_language", "en"),
            segments=segments,
            usage=UsageMetrics(provider=self.name, model=params["model"], seconds=float(body.get("metadata", {}).get("duration") or 0), latency_ms=done()),
        )
