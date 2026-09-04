"""Replicate adapter (FLUX, SDXL ...). Uses the predictions API with polling."""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.providers.base import (
    ImageProvider,
    ImageResult,
    ProviderPermanentError,
    ProviderTransientError,
    UsageMetrics,
    provider_retry,
)
from app.providers.http import request_bytes, request_json

REPLICATE_API = "https://api.replicate.com/v1"


def replicate_run(model: str, inputs: dict[str, Any], *, token: str, timeout: float = 600) -> Any:
    """Create a prediction for `owner/name[:version]` and poll until done. Returns `output`."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Prefer": "wait=60"}
    if ":" in model:
        _, version = model.split(":", 1)
        url, body = f"{REPLICATE_API}/predictions", {"version": version, "input": inputs}
    else:
        url, body = f"{REPLICATE_API}/models/{model}/predictions", {"input": inputs}
    pred = request_json("POST", url, provider="replicate", headers=headers, json=body)
    deadline = time.time() + timeout
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise ProviderTransientError("replicate: prediction timed out")
        time.sleep(2.0)
        pred = request_json("GET", pred["urls"]["get"], provider="replicate", headers=headers)
    if pred.get("status") != "succeeded":
        raise ProviderPermanentError(f"replicate: prediction {pred.get('status')}: {pred.get('error')}")
    return pred.get("output"), pred


class ReplicateImageProvider(ImageProvider):
    name = "replicate"
    display_name = "Replicate (FLUX / SDXL)"

    def __init__(self, *, token: str | None = None, model: str | None = None):
        self.token = token or settings.replicate_api_token
        self.model = model or settings.replicate_image_model

    def is_configured(self) -> bool:
        return bool(self.token)

    def capabilities(self) -> dict[str, Any]:
        return {"aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:2"], "seed": True, "negative_prompt": True}

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
        r = width / max(1, height)
        aspect = "16:9" if r > 1.5 else "4:3" if r > 1.2 else "1:1" if r > 0.85 else "9:16"
        inputs: dict[str, Any] = {
            "prompt": prompt if not style else f"{prompt}, {style}",
            "aspect_ratio": aspect,
            "output_format": "png",
            "num_outputs": 1,
        }
        if negative_prompt:
            inputs["negative_prompt"] = negative_prompt
        if seed is not None:
            inputs["seed"] = seed
        output, pred = replicate_run(model or self.model, inputs, token=self.token or "")
        url = output[0] if isinstance(output, list) else output
        if not isinstance(url, str):
            raise ProviderPermanentError("replicate: no image URL in output")
        data, ctype = request_bytes("GET", url, provider=self.name)
        return ImageResult(
            data=data,
            content_type=ctype or "image/png",
            width=width,
            height=height,
            seed=seed,
            provider_ref=pred.get("id"),
            usage=UsageMetrics(provider=self.name, model=model or self.model, images=1, latency_ms=done(), raw={"metrics": pred.get("metrics", {})}),
        )
