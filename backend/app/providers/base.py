"""Abstract provider interfaces and the data types they exchange.

All providers are *synchronous* because they are executed inside Celery workers.
The API layer never calls a provider directly - it enqueues a job instead.
"""

from __future__ import annotations

import abc
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import ProviderError


class ProviderTransientError(ProviderError):
    """Raised for retryable failures (rate limits, 5xx, timeouts)."""


class ProviderPermanentError(ProviderError):
    """Raised for non-retryable failures (bad request, content policy, auth)."""


def provider_retry(fn: Callable) -> Callable:
    """Retry decorator used by concrete adapters for transient errors."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(max(1, settings.provider_max_retries)),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(ProviderTransientError),
    )(fn)


# --------------------------------------------------------------------------
# Shared value objects
# --------------------------------------------------------------------------


@dataclass
class ProviderInfo:
    name: str
    display_name: str
    kind: str
    is_mock: bool = False
    is_configured: bool = True
    default_model: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageMetrics:
    """Returned by every provider call so the billing service can meter it."""

    provider: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    characters: int = 0
    images: int = 0
    seconds: float = 0.0
    latency_ms: float = 0.0
    cost_usd: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMResult:
    text: str
    usage: UsageMetrics
    parsed: Any | None = None  # populated when json_mode=True


@dataclass
class ImageResult:
    data: bytes
    content_type: str
    width: int
    height: int
    usage: UsageMetrics
    seed: int | None = None
    provider_ref: str | None = None
    revised_prompt: str | None = None


@dataclass
class VideoResult:
    data: bytes
    content_type: str
    width: int
    height: int
    duration_seconds: float
    fps: float
    usage: UsageMetrics
    provider_ref: str | None = None


@dataclass
class VoiceInfo:
    id: str
    name: str
    language: str
    gender: str | None = None
    accent: str | None = None
    styles: list[str] = field(default_factory=list)
    preview_url: str | None = None
    provider: str = ""
    is_premium: bool = False


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class TTSResult:
    data: bytes
    content_type: str
    duration_seconds: float
    usage: UsageMetrics
    sample_rate: int = 24000
    word_timings: list[WordTiming] = field(default_factory=list)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: list[WordTiming] = field(default_factory=list)


@dataclass
class STTResult:
    text: str
    language: str
    segments: list[TranscriptSegment]
    usage: UsageMetrics


@dataclass
class StockMediaItem:
    id: str
    kind: Literal["image", "video"]
    url: str
    download_url: str
    thumbnail_url: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    author: str | None
    source: str
    license: str = ""


# --------------------------------------------------------------------------
# Interfaces
# --------------------------------------------------------------------------


class BaseProvider(abc.ABC):
    kind: str = "base"
    name: str = "base"
    display_name: str = "Base"
    is_mock: bool = False

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self.name,
            display_name=self.display_name,
            kind=self.kind,
            is_mock=self.is_mock,
            is_configured=self.is_configured(),
            default_model=getattr(self, "model", None),
            capabilities=self.capabilities(),
        )

    def is_configured(self) -> bool:
        return True

    def capabilities(self) -> dict[str, Any]:
        return {}

    def health_check(self) -> bool:
        return self.is_configured()

    @staticmethod
    def _timer() -> Callable[[], float]:
        start = time.perf_counter()
        return lambda: (time.perf_counter() - start) * 1000.0


class LLMProvider(BaseProvider):
    kind = "llm"

    @abc.abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        model: str | None = None,
    ) -> LLMResult: ...

    def stream(self, messages: list[LLMMessage], **kwargs: Any) -> Iterator[str]:
        """Default streaming falls back to a single chunk."""
        yield self.complete(messages, **kwargs).text


class ImageProvider(BaseProvider):
    kind = "image"

    @abc.abstractmethod
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
    ) -> ImageResult: ...


class VideoProvider(BaseProvider):
    kind = "video"

    @abc.abstractmethod
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
    ) -> VideoResult: ...


class TTSProvider(BaseProvider):
    kind = "tts"

    @abc.abstractmethod
    def list_voices(self, language: str | None = None) -> list[VoiceInfo]: ...

    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        language: str = "en",
        speed: float = 1.0,
        style: str | None = None,
        output_format: str = "mp3",
        model: str | None = None,
    ) -> TTSResult: ...


class STTProvider(BaseProvider):
    kind = "stt"

    @abc.abstractmethod
    def transcribe(
        self,
        audio: bytes,
        *,
        content_type: str = "audio/mpeg",
        language: str | None = None,
        prompt: str | None = None,
        word_timestamps: bool = True,
        model: str | None = None,
    ) -> STTResult: ...


class StockMediaProvider(BaseProvider):
    kind = "stock"

    @abc.abstractmethod
    def search(
        self,
        query: str,
        *,
        kind: Literal["image", "video"] = "video",
        orientation: str = "landscape",
        per_page: int = 10,
        page: int = 1,
        min_duration: float | None = None,
    ) -> list[StockMediaItem]: ...

    @abc.abstractmethod
    def download(self, item: StockMediaItem) -> tuple[bytes, str]:
        """Return (bytes, content_type)."""
