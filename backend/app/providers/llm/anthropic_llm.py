"""Anthropic Messages API adapter."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import settings
from app.providers.base import LLMMessage, LLMProvider, LLMResult, ProviderPermanentError, UsageMetrics, provider_retry
from app.providers.http import request_json


class AnthropicLLMProvider(LLMProvider):
    name = "anthropic"
    display_name = "Anthropic Claude"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"json_mode": True, "streaming": True}

    @provider_retry
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResult:
        done = self._timer()
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        if json_mode:
            system += "\n\nRespond with a single valid JSON object and nothing else."
        convo = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        data = request_json(
            "POST",
            "https://api.anthropic.com/v1/messages",
            provider=self.name,
            headers={
                "x-api-key": self.api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model or self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system or None,
                "messages": convo,
            },
        )
        try:
            text = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise ProviderPermanentError("anthropic: unexpected response shape") from exc
        parsed = None
        if json_mode:
            candidate = text.strip()
            fence = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.S)
            if fence:
                candidate = fence.group(1)
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise ProviderPermanentError("anthropic: model returned invalid JSON") from exc
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            parsed=parsed,
            usage=UsageMetrics(
                provider=self.name,
                model=data.get("model") or self.model,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                latency_ms=done(),
                raw=usage,
            ),
        )
