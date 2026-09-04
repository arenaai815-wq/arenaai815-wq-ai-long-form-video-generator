"""AI provider abstraction layer.

Every external capability (LLM, image, video, TTS, STT, stock media) is accessed
through an abstract interface defined in `app.providers.base`. Concrete adapters
live in per-capability subpackages and are selected via environment variables
(`LLM_PROVIDER`, `IMAGE_PROVIDER`, ...). `app.providers.registry` wires them up.

The mock providers produce real, deterministic artifacts (text, PNGs, WAVs, MP4s)
so the whole pipeline - including FFmpeg rendering - runs without any API keys.
"""

from app.providers.registry import ProviderRegistry, get_registry

__all__ = ["ProviderRegistry", "get_registry"]
