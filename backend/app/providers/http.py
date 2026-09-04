"""Shared HTTP client helpers for real provider adapters."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.providers.base import ProviderPermanentError, ProviderTransientError

_RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}


def client(timeout: float | None = None, **kwargs: Any) -> httpx.Client:
    return httpx.Client(timeout=timeout or settings.provider_timeout_seconds, follow_redirects=True, **kwargs)


def raise_for_provider(resp: httpx.Response, provider: str) -> None:
    if resp.is_success:
        return
    body = resp.text[:800]
    msg = f"{provider} HTTP {resp.status_code}: {body}"
    if resp.status_code in _RETRYABLE:
        raise ProviderTransientError(msg)
    raise ProviderPermanentError(msg)


def request_json(method: str, url: str, *, provider: str, timeout: float | None = None, **kwargs: Any) -> Any:
    try:
        with client(timeout) as c:
            resp = c.request(method, url, **kwargs)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise ProviderTransientError(f"{provider} network error: {exc}") from exc
    raise_for_provider(resp, provider)
    if not resp.content:
        return None
    return resp.json()


def request_bytes(method: str, url: str, *, provider: str, timeout: float | None = None, **kwargs: Any) -> tuple[bytes, str]:
    try:
        with client(timeout) as c:
            resp = c.request(method, url, **kwargs)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise ProviderTransientError(f"{provider} network error: {exc}") from exc
    raise_for_provider(resp, provider)
    return resp.content, resp.headers.get("content-type", "application/octet-stream").split(";")[0]
