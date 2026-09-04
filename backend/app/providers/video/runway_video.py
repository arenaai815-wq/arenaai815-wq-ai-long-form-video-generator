"""Runway Gen-3/Gen-4 image-to-video adapter."""

from __future__ import annotations

import base64
import time
from typing import Any

from app.core.config import settings
from app.providers.base import (
    ProviderPermanentError,
    ProviderTransientError,
    UsageMetrics,
    VideoProvider,
    VideoResult,
    provider_retry,
)
from app.providers.http import request_bytes, request_json

API = "https://api.dev.runwayml.com/v1"
VERSION = "2024-11-06"


class RunwayVideoProvider(VideoProvider):
    name = "runway"
    display_name = "Runway Gen-4"

    def __init__(self, *, api_key: str | None = None, model: str = "gen4_turbo"):
        self.api_key = api_key or settings.runway_api_key
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"image_to_video": True, "text_to_video": False, "durations": [5, 10]}

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
        if not image:
            raise ProviderPermanentError("runway: an input image is required (image-to-video)")
        done = self._timer()
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Runway-Version": VERSION, "Content-Type": "application/json"}
        duration = 10 if duration_seconds > 7 else 5
        ratio = "1280:720" if width >= height else "720:1280"
        task = request_json(
            "POST",
            f"{API}/image_to_video",
            provider=self.name,
            headers=headers,
            json={
                "model": model or self.model,
                "promptImage": "data:image/png;base64," + base64.b64encode(image).decode(),
                "promptText": prompt[:1000],
                "duration": duration,
                "ratio": ratio,
            },
        )
        task_id = task["id"]
        deadline = time.time() + 1200
        while True:
            if time.time() > deadline:
                raise ProviderTransientError("runway: task timed out")
            time.sleep(5)
            status = request_json("GET", f"{API}/tasks/{task_id}", provider=self.name, headers=headers)
            if status.get("status") == "SUCCEEDED":
                url = (status.get("output") or [None])[0]
                break
            if status.get("status") in ("FAILED", "CANCELLED"):
                raise ProviderPermanentError(f"runway: {status.get('failure') or status.get('status')}")
        if not url:
            raise ProviderPermanentError("runway: no output")
        data, ctype = request_bytes("GET", url, provider=self.name, timeout=600)
        w, h = (int(x) for x in ratio.split(":"))
        return VideoResult(
            data=data,
            content_type=ctype or "video/mp4",
            width=w,
            height=h,
            duration_seconds=float(duration),
            fps=24.0,
            provider_ref=task_id,
            usage=UsageMetrics(provider=self.name, model=model or self.model, seconds=float(duration), latency_ms=done()),
        )
