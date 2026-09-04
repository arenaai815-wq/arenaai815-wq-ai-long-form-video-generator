"""OpenAI (and OpenAI-compatible: Groq, Together, Ollama, vLLM, OpenRouter...) chat completions."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.providers.base import (
    LLMMessage,
    LLMProvider,
    LLMResult,
    ProviderPermanentError,
    UsageMetrics,
    provider_retry,
)
from app.providers.http import request_json


class OpenAILLMProvider(LLMProvider):
    name = "openai"
    display_name = "OpenAI Chat Completions"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, model: str | None = None, name: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = model or settings.openai_llm_model
        if name:
            self.name = name
            self.display_name = f"OpenAI-compatible ({name})"

    def is_configured(self) -> bool:
        return bool(self.api_key) or "localhost" in self.base_url or "127.0.0.1" in self.base_url

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
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = request_json(
            "POST",
            f"{self.base_url}/chat/completions",
            provider=self.name,
            headers={"Authorization": f"Bearer {self.api_key or 'none'}", "Content-Type": "application/json"},
            json=body,
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderPermanentError(f"{self.name}: unexpected response shape") from exc
        parsed = None
        if json_mode:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProviderPermanentError(f"{self.name}: model returned invalid JSON") from exc
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            parsed=parsed,
            usage=UsageMetrics(
                provider=self.name,
                model=data.get("model") or body["model"],
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                latency_ms=done(),
                raw=usage,
            ),
        )
