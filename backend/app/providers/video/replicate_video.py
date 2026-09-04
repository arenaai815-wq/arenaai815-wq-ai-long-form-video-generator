"""Replicate-hosted video models (Minimax, Kling, Wan, LTX...)."""

from __future__ import annotations

import base64
from typing import Any

from app.core.config import settings
from app.providers.base import ProviderPermanentError, UsageMetrics, VideoProvider, VideoResult, provider_retry
from app.providers.http import request_bytes
from app.providers.image.replicate_image import replicate_run


class ReplicateVideoProvider(VideoProvider):
    name = "replicate"
    display_name = "Replicate Video (Minimax / Kling / Wan)"

    def __init__(self, *, token: str | None = None, model: str | None = None):
        self.token = token or settings.replicate_api_token
        self.model = model or settings.replicate_video_model

    def is_configured(self) -> bool:
        return bool(self.token)

    def capabilities(self) -> dict[str, Any]:
        return {"image_to_video": True, "max_duration": 10}

    @provider_retry
    def generate_video(
        self,
        prompt: str,
        *,
        width: int = 1280,
        height: int = 720,
        duration_seconds: float = 5.0,
        fps: int = 24,
        image: bytes | None = None,
        style: str | None = None,
        model: str | None = None,
    ) -> VideoResult:
        done = self._timer()
        inputs: dict[str, Any] = {"prompt": prompt if not style else f"{prompt}, {style}"}
        if image:
            inputs["first_frame_image"] = "data:image/png;base64," + base64.b64encode(image).decode()
        inputs["duration"] = int(max(1, min(10, round(duration_seconds))))
        inputs["aspect_ratio"] = "16:9" if width >= height else "9:16"
        output, pred = replicate_run(model or self.model, inputs, token=self.token or "", timeout=1200)
        url = output[0] if isinstance(output, list) else output
        if not isinstance(url, str):
            raise ProviderPermanentError("replicate video: no output URL")
        data, ctype = request_bytes("GET", url, provider=self.name, timeout=600)
        return VideoResult(
            data=data,
            content_type=ctype or "video/mp4",
            width=width,
            height=height,
            duration_seconds=float(inputs["duration"]),
            fps=float(fps),
            provider_ref=pred.get("id"),
            usage=UsageMetrics(provider=self.name, model=model or self.model, seconds=float(inputs["duration"]), latency_ms=done()),
        )
