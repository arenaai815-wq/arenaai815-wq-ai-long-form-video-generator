"""Pexels stock photo/video adapter."""

from __future__ import annotations

from typing import Any, Literal

from app.core.config import settings
from app.providers.base import StockMediaItem, StockMediaProvider, provider_retry
from app.providers.http import request_bytes, request_json


class PexelsStockProvider(StockMediaProvider):
    name = "pexels"
    display_name = "Pexels"

    def __init__(self, *, api_key: str | None = None):
        self.api_key = api_key or settings.pexels_api_key

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> dict[str, Any]:
        return {"kinds": ["image", "video"], "orientations": ["landscape", "portrait", "square"], "license": "Pexels License"}

    @provider_retry
    def search(
        self,
        query: str,
        *,
        kind: Literal["image", "video"] = "video",
        orientation: str = "landscape",
        per_page: int = 10,
        page: int = 1,
        min_duration: float | None = None,
    ) -> list[StockMediaItem]:
        headers = {"Authorization": self.api_key or ""}
        params: dict[str, Any] = {"query": query, "per_page": per_page, "page": page, "orientation": orientation}
        items: list[StockMediaItem] = []
        if kind == "video":
            if min_duration:
                params["min_duration"] = int(min_duration)
            data = request_json("GET", "https://api.pexels.com/videos/search", provider=self.name, headers=headers, params=params)
            for v in data.get("videos", []):
                files = sorted(v.get("video_files", []), key=lambda f: (f.get("width") or 0), reverse=True)
                best = next((f for f in files if (f.get("width") or 0) <= 1920), files[0] if files else None)
                if not best:
                    continue
                items.append(
                    StockMediaItem(
                        id=str(v["id"]),
                        kind="video",
                        url=v.get("url", ""),
                        download_url=best["link"],
                        thumbnail_url=v.get("image"),
                        width=best.get("width"),
                        height=best.get("height"),
                        duration_seconds=float(v.get("duration") or 0),
                        author=(v.get("user") or {}).get("name"),
                        source=self.name,
                        license="Pexels License",
                    )
                )
        else:
            data = request_json("GET", "https://api.pexels.com/v1/search", provider=self.name, headers=headers, params=params)
            for p in data.get("photos", []):
                items.append(
                    StockMediaItem(
                        id=str(p["id"]),
                        kind="image",
                        url=p.get("url", ""),
                        download_url=p["src"].get("large2x") or p["src"].get("original"),
                        thumbnail_url=p["src"].get("medium"),
                        width=p.get("width"),
                        height=p.get("height"),
                        duration_seconds=None,
                        author=p.get("photographer"),
                        source=self.name,
                        license="Pexels License",
                    )
                )
        return items

    def download(self, item: StockMediaItem) -> tuple[bytes, str]:
        return request_bytes("GET", item.download_url, provider=self.name, timeout=600)
