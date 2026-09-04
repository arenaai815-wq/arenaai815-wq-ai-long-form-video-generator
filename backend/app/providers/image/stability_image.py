"""Stability AI (Stable Image Core / SD3) adapter."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ImageProvider, ImageResult, ProviderTransientError, UsageMetrics, provider_retry
from app.providers.http import client, raise_for_provider

_ASPECTS = ["16:9", "1:1", "21:9", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"]


def _closest(width: int, height: int) -> str:
    target = width / max(1, height)
    best = min(_ASPECTS, key=lambda a: abs((int(a.split(":")[0]) / int(a.split(":")[1])) - target))
    return best


class StabilityImageProvider(ImageProvider):
    name = "stability"
    display_name = "Stability AI"

    def __init__(self, *, api_key: str | None = None, model: str = "core"):
        self.api_key = api_key or settings.stability_api_key
        self.model = model  # core | sd3 | ultra

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"aspect_ratios": _ASPECTS, "negative_prompt": True, "seed": True, "style_presets": True}

    @provider_retry
    def generate_image(
        self,
        prompt: str,
        *,
        width: int = 1920,
        height: int = 1080,
        style: str | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        model: str | None = None,
    ) -> ImageResult:
        done = self._timer()
        mdl = model or self.model
        url = f"https://api.stability.ai/v2beta/stable-image/generate/{mdl}"
        fields: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": _closest(width, height),
            "output_format": "png",
        }
        if negative_prompt:
            fields["negative_prompt"] = negative_prompt
        if seed is not None:
            fields["seed"] = str(seed)
        if style and mdl == "core":
            fields["style_preset"] = _style_preset(style)
        try:
            with client(240) as c:
                resp = c.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Accept": "image/*"},
                    files={"none": ""},
                    data=fields,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransientError(f"stability network error: {exc}") from exc
        raise_for_provider(resp, self.name)
        # Stability doesn't return dimensions; read from PNG header
        w, h = _png_size(resp.content) or (width, height)
        return ImageResult(
            data=resp.content,
            content_type="image/png",
            width=w,
            height=h,
            seed=int(resp.headers.get("seed", seed or 0)) or None,
            usage=UsageMetrics(provider=self.name, model=mdl, images=1, latency_ms=done()),
        )


def _style_preset(style: str) -> str:
    s = style.lower()
    mapping = {
        "cinematic": "cinematic",
        "photorealistic": "photographic",
        "realistic": "photographic",
        "anime": "anime",
        "3d": "3d-model",
        "digital": "digital-art",
        "comic": "comic-book",
        "fantasy": "fantasy-art",
        "documentary": "photographic",
        "illustration": "digital-art",
        "watercolor": "analog-film",
    }
    for k, v in mapping.items():
        if k in s:
            return v
    return "cinematic"


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return None
