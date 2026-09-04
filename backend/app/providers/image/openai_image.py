"""OpenAI Images API (gpt-image-1 / dall-e-3)."""

from __future__ import annotations

import base64
from typing import Any

from app.core.config import settings
from app.providers.base import ImageProvider, ImageResult, ProviderPermanentError, UsageMetrics, provider_retry
from app.providers.http import request_bytes, request_json

_SIZES = {"16:9": "1536x1024", "9:16": "1024x1536", "1:1": "1024x1024"}
_DALLE_SIZES = {"16:9": "1792x1024", "9:16": "1024x1792", "1:1": "1024x1024"}


def _closest_aspect(width: int, height: int) -> str:
    r = width / max(1, height)
    if r > 1.3:
        return "16:9"
    if r < 0.8:
        return "9:16"
    return "1:1"


class OpenAIImageProvider(ImageProvider):
    name = "openai"
    display_name = "OpenAI Images"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_image_model
        self.base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"sizes": list(_SIZES.values()), "negative_prompt": False}

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
        aspect = _closest_aspect(width, height)
        size = (_DALLE_SIZES if "dall-e" in mdl else _SIZES)[aspect]
        full_prompt = prompt if not style else f"{prompt}. Style: {style}."
        if negative_prompt:
            full_prompt += f" Avoid: {negative_prompt}."
        body: dict[str, Any] = {"model": mdl, "prompt": full_prompt, "n": 1, "size": size}
        if "dall-e" in mdl:
            body["response_format"] = "b64_json"
            body["quality"] = "hd"
        else:
            body["quality"] = "high"
        data = request_json(
            "POST",
            f"{self.base_url}/images/generations",
            provider=self.name,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=240,
        )
        try:
            item = data["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderPermanentError("openai images: unexpected response") from exc
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
            ctype = "image/png"
        else:
            raw, ctype = request_bytes("GET", item["url"], provider=self.name)
        w, h = (int(x) for x in size.split("x"))
        return ImageResult(
            data=raw,
            content_type=ctype,
            width=w,
            height=h,
            revised_prompt=item.get("revised_prompt"),
            usage=UsageMetrics(provider=self.name, model=mdl, images=1, latency_ms=done()),
        )
