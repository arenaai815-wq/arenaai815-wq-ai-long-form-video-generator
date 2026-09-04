"""Real provider adapters exercised hermetically through httpx.MockTransport.

These verify the request wiring (auth headers, payload shape), response mapping into the
provider value objects, and the transient/permanent error classification + retry policy that
the worker layer relies on. No network access."""
from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from app.providers import http as phttp
from app.providers.base import LLMMessage, ProviderPermanentError, ProviderTransientError


class FakeAPI:
    """Route table for MockTransport; records every request it served."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Any] = {}
        self.calls: list[httpx.Request] = []

    def on(self, method: str, path: str, handler: Any) -> None:
        self.routes[(method, path)] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        handler = self.routes.get((request.method, request.url.path))
        if handler is None:
            return httpx.Response(404, json={"error": f"no route {request.method} {request.url.path}"})
        return handler(request) if callable(handler) else handler


@pytest.fixture
def api(monkeypatch):
    fake = FakeAPI()

    def client(timeout: float | None = None, **kwargs: Any) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(fake), timeout=timeout or 5, **kwargs)

    monkeypatch.setattr(phttp, "client", client)
    # tenacity waits between retries; make them instant
    from app.providers import base as pbase

    monkeypatch.setattr(pbase.settings, "provider_max_retries", 3, raising=False)
    return fake


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_: None)


# ------------------------------------------------------------------ http helpers


def test_error_classification(api):
    api.on("GET", "/rate", httpx.Response(429, text="slow down"))
    api.on("GET", "/bad", httpx.Response(400, text="bad prompt"))
    api.on("GET", "/down", httpx.Response(503, text="maintenance"))
    with pytest.raises(ProviderTransientError):
        phttp.request_json("GET", "https://x.test/rate", provider="t")
    with pytest.raises(ProviderTransientError):
        phttp.request_json("GET", "https://x.test/down", provider="t")
    with pytest.raises(ProviderPermanentError, match="bad prompt"):
        phttp.request_json("GET", "https://x.test/bad", provider="t")


def test_network_errors_are_transient(api):
    def boom(_req):
        raise httpx.ConnectError("refused")

    api.on("GET", "/net", boom)
    with pytest.raises(ProviderTransientError, match="network error"):
        phttp.request_json("GET", "https://x.test/net", provider="t")


# ------------------------------------------------------------------ OpenAI images


def test_openai_image_maps_response_and_retries_transient(api, monkeypatch):
    from app.providers.image.openai_image import OpenAIImageProvider

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    attempts = {"n": 0}

    def gen(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        assert request.headers["Authorization"] == "Bearer sk-test"
        body = json.loads(request.content)
        assert body["model"] == "gpt-image-1" and body["n"] == 1
        assert "Style: watercolor" in body["prompt"]
        if attempts["n"] == 1:
            return httpx.Response(500, text="try again")
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode(), "revised_prompt": "a vent"}]})

    api.on("POST", "/v1/images/generations", gen)
    p = OpenAIImageProvider(api_key="sk-test", model="gpt-image-1")
    monkeypatch.setattr(p, "base_url", "https://x.test/v1")
    res = p.generate_image("deep sea vent", width=1920, height=1080, style="watercolor")
    assert attempts["n"] == 2  # one transient failure, then success
    assert res.data == png and res.content_type == "image/png"
    assert (res.width, res.height) == (1536, 1024)  # closest supported landscape size
    assert res.revised_prompt == "a vent"
    assert res.usage.images == 1 and res.usage.provider == "openai"


def test_openai_image_permanent_error_not_retried(api, monkeypatch):
    from app.providers.image.openai_image import OpenAIImageProvider

    api.on("POST", "/v1/images/generations", httpx.Response(400, json={"error": {"message": "content policy"}}))
    p = OpenAIImageProvider(api_key="sk-test", model="gpt-image-1")
    monkeypatch.setattr(p, "base_url", "https://x.test/v1")
    with pytest.raises(ProviderPermanentError, match="content policy"):
        p.generate_image("x")
    assert len(api.calls) == 1


# ------------------------------------------------------------------ OpenAI-compatible LLM


def test_openai_llm_json_mode_parses_and_counts_tokens(api):
    from app.providers.llm.openai_llm import OpenAILLMProvider

    def chat(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0] == {"role": "system", "content": "You research."}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"sections": [{"title": "Origins"}]}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7},
            },
        )

    api.on("POST", "/v1/chat/completions", chat)
    p = OpenAILLMProvider(api_key="k", base_url="https://x.test/v1", model="gpt-4o-mini")
    res = p.complete([LLMMessage("system", "You research."), LLMMessage("user", "vents")], json_mode=True)
    assert res.parsed == {"sections": [{"title": "Origins"}]}
    assert res.usage.input_tokens == 12 and res.usage.output_tokens == 7


def test_openai_llm_invalid_json_is_permanent(api):
    from app.providers.llm.openai_llm import OpenAILLMProvider

    api.on("POST", "/v1/chat/completions", httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}))
    p = OpenAILLMProvider(api_key="k", base_url="https://x.test/v1", model="m")
    with pytest.raises(ProviderPermanentError, match="invalid JSON"):
        p.complete([LLMMessage("user", "hi")], json_mode=True)


# ------------------------------------------------------------------ ElevenLabs TTS


def test_elevenlabs_word_timings_from_character_alignment(api, monkeypatch):
    from app.providers.tts import elevenlabs_tts as el

    monkeypatch.setattr(el, "_probe_duration", lambda *_: 1.25)
    text = "Hi there"
    chars = list(text)
    starts = [i * 0.1 for i in range(len(chars))]
    ends = [s + 0.1 for s in starts]

    def tts(request: httpx.Request) -> httpx.Response:
        assert request.headers["xi-api-key"] == "xi-test"
        assert request.url.params["output_format"] == "mp3_44100_128"
        body = json.loads(request.content)
        assert body["text"] == text and 0.7 <= body["voice_settings"]["speed"] <= 1.2
        return httpx.Response(
            200,
            json={
                "audio_base64": base64.b64encode(b"ID3fake").decode(),
                "alignment": {"characters": chars, "character_start_times_seconds": starts, "character_end_times_seconds": ends},
            },
        )

    api.on("POST", "/v1/text-to-speech/voice123/with-timestamps", tts)
    monkeypatch.setattr(el, "API", "https://x.test/v1")
    p = el.ElevenLabsTTSProvider(api_key="xi-test")
    res = p.synthesize(text, voice_id="voice123", speed=1.9)
    assert res.data == b"ID3fake" and res.duration_seconds == 1.25
    assert [w.word for w in res.word_timings] == ["Hi", "there"]
    assert res.word_timings[0].start == pytest.approx(0.0) and res.word_timings[1].start == pytest.approx(0.3)
    assert res.usage.characters == len(text)


# ------------------------------------------------------------------ Pexels stock


def test_pexels_video_search_picks_best_file_under_1080p(api):
    from app.providers.stock.pexels_stock import PexelsStockProvider

    def search(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "px-test"
        assert request.url.params["orientation"] == "portrait" and request.url.params["query"] == "ocean"
        return httpx.Response(
            200,
            json={
                "videos": [
                    {
                        "id": 42,
                        "url": "https://pexels.test/v/42",
                        "image": "https://pexels.test/t/42.jpg",
                        "duration": 12,
                        "user": {"name": "Ada"},
                        "video_files": [
                            {"link": "https://cdn/4k.mp4", "width": 3840, "height": 2160},
                            {"link": "https://cdn/hd.mp4", "width": 1920, "height": 1080},
                            {"link": "https://cdn/sd.mp4", "width": 640, "height": 360},
                        ],
                    },
                    {"id": 43, "video_files": []},  # no files -> skipped
                ]
            },
        )

    api.on("GET", "/videos/search", search)
    items = PexelsStockProvider(api_key="px-test").search("ocean", kind="video", orientation="portrait")
    assert len(items) == 1
    it = items[0]
    assert it.id == "42" and it.kind == "video" and it.download_url == "https://cdn/hd.mp4"
    assert (it.width, it.height, it.duration_seconds) == (1920, 1080, 12.0)
    assert it.author == "Ada" and it.source == "pexels" and it.license == "Pexels License"
