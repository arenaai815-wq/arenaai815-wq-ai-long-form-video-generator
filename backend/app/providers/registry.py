"""Provider registry: resolves the configured adapter for each capability.

Selection is driven by env vars (`LLM_PROVIDER`, `IMAGE_PROVIDER`, `VIDEO_PROVIDER`,
`TTS_PROVIDER`, `STT_PROVIDER`, `STOCK_PROVIDER`). Unknown or unconfigured providers
fall back to the mock provider with a warning so development never hard-fails.
Adding a provider = write an adapter class + register a factory below.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import (
    BaseProvider,
    ImageProvider,
    LLMProvider,
    ProviderInfo,
    StockMediaProvider,
    STTProvider,
    TTSProvider,
    VideoProvider,
)

log = get_logger(__name__)
T = TypeVar("T", bound=BaseProvider)

Factory = Callable[[], BaseProvider]


def _llm_factories() -> dict[str, Factory]:
    from app.providers.llm.anthropic_llm import AnthropicLLMProvider
    from app.providers.llm.openai_llm import OpenAILLMProvider
    from app.providers.mock.llm import MockLLMProvider

    return {
        "mock": MockLLMProvider,
        "openai": OpenAILLMProvider,
        "anthropic": AnthropicLLMProvider,
        # Any OpenAI-compatible server (Groq, Together, OpenRouter, Ollama, vLLM)
        "openai_compatible": lambda: OpenAILLMProvider(name="openai_compatible"),
    }


def _image_factories() -> dict[str, Factory]:
    from app.providers.image.openai_image import OpenAIImageProvider
    from app.providers.image.replicate_image import ReplicateImageProvider
    from app.providers.image.stability_image import StabilityImageProvider
    from app.providers.mock.image import MockImageProvider

    return {
        "mock": MockImageProvider,
        "openai": OpenAIImageProvider,
        "stability": StabilityImageProvider,
        "replicate": ReplicateImageProvider,
    }


def _video_factories() -> dict[str, Factory]:
    from app.providers.mock.video import MockVideoProvider
    from app.providers.video.replicate_video import ReplicateVideoProvider
    from app.providers.video.runway_video import RunwayVideoProvider

    return {
        "mock": MockVideoProvider,
        "replicate": ReplicateVideoProvider,
        "runway": RunwayVideoProvider,
    }


def _tts_factories() -> dict[str, Factory]:
    from app.providers.mock.tts import MockTTSProvider
    from app.providers.tts.elevenlabs_tts import ElevenLabsTTSProvider
    from app.providers.tts.openai_tts import OpenAITTSProvider

    return {
        "mock": MockTTSProvider,
        "openai": OpenAITTSProvider,
        "elevenlabs": ElevenLabsTTSProvider,
    }


def _stt_factories() -> dict[str, Factory]:
    from app.providers.mock.stt import MockSTTProvider
    from app.providers.stt.deepgram_stt import DeepgramSTTProvider
    from app.providers.stt.openai_stt import OpenAISTTProvider

    return {
        "mock": MockSTTProvider,
        "openai_whisper": OpenAISTTProvider,
        "openai": OpenAISTTProvider,
        "deepgram": DeepgramSTTProvider,
    }


def _stock_factories() -> dict[str, Factory]:
    from app.providers.mock.stock import MockStockProvider
    from app.providers.stock.pexels_stock import PexelsStockProvider

    return {
        "mock": MockStockProvider,
        "pexels": PexelsStockProvider,
    }


FACTORIES: dict[str, Callable[[], dict[str, Factory]]] = {
    "llm": _llm_factories,
    "image": _image_factories,
    "video": _video_factories,
    "tts": _tts_factories,
    "stt": _stt_factories,
    "stock": _stock_factories,
}


class ProviderRegistry:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], BaseProvider] = {}

    # ---- resolution ----------------------------------------------------
    def _configured_name(self, kind: str) -> str:
        return {
            "llm": settings.llm_provider,
            "image": settings.image_provider,
            "video": settings.video_provider,
            "tts": settings.tts_provider,
            "stt": settings.stt_provider,
            "stock": settings.stock_provider,
        }[kind].lower()

    def get(self, kind: str, name: str | None = None) -> BaseProvider:
        name = (name or self._configured_name(kind)).lower()
        key = (kind, name)
        if key in self._cache:
            return self._cache[key]
        factories = FACTORIES[kind]()
        factory = factories.get(name)
        if factory is None:
            log.warning("unknown provider, falling back to mock", kind=kind, name=name)
            factory = factories["mock"]
        provider = factory()
        if not provider.is_configured():
            if name != "mock":
                log.warning("provider not configured (missing API key); using mock", kind=kind, name=name)
            provider = factories["mock"]()
        self._cache[key] = provider
        return provider

    def llm(self, name: str | None = None) -> LLMProvider:
        return self.get("llm", name)  # type: ignore[return-value]

    def image(self, name: str | None = None) -> ImageProvider:
        return self.get("image", name)  # type: ignore[return-value]

    def video(self, name: str | None = None) -> VideoProvider:
        return self.get("video", name)  # type: ignore[return-value]

    def tts(self, name: str | None = None) -> TTSProvider:
        return self.get("tts", name)  # type: ignore[return-value]

    def stt(self, name: str | None = None) -> STTProvider:
        return self.get("stt", name)  # type: ignore[return-value]

    def stock(self, name: str | None = None) -> StockMediaProvider:
        return self.get("stock", name)  # type: ignore[return-value]

    # ---- introspection -------------------------------------------------
    def available(self) -> dict[str, list[ProviderInfo]]:
        """Describe every registered adapter and whether it is configured (no secrets)."""
        out: dict[str, list[ProviderInfo]] = {}
        for kind, loader in FACTORIES.items():
            infos = []
            active = self._configured_name(kind)
            for name, factory in loader().items():
                try:
                    p = factory()
                    info = p.info()
                    info.capabilities = {**info.capabilities, "active": name == active}
                    infos.append(info)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning("provider factory failed", kind=kind, name=name, error=str(exc))
            out[kind] = infos
        return out

    def active(self) -> dict[str, dict[str, Any]]:
        result = {}
        for kind in FACTORIES:
            p = self.get(kind)
            result[kind] = {"name": p.name, "display_name": p.display_name, "is_mock": p.is_mock, "model": getattr(p, "model", None)}
        return result


@lru_cache
def get_registry() -> ProviderRegistry:
    return ProviderRegistry()
