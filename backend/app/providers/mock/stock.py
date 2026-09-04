"""Mock stock media provider - returns locally generated placeholder assets."""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from app.providers.base import StockMediaItem, StockMediaProvider
from app.providers.mock.image import render_placeholder
from app.providers.mock.video import MockVideoProvider


class MockStockProvider(StockMediaProvider):
    name = "mock"
    display_name = "Mock Stock Library (development)"
    is_mock = True

    def capabilities(self) -> dict[str, Any]:
        return {"kinds": ["image", "video"], "orientations": ["landscape", "portrait", "square"]}

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
        w, h = (1920, 1080) if orientation == "landscape" else (1080, 1920) if orientation == "portrait" else (1080, 1080)
        items = []
        for i in range(per_page):
            ident = hashlib.md5(f"{query}:{kind}:{page}:{i}".encode()).hexdigest()[:12]
            items.append(
                StockMediaItem(
                    id=f"mock-{kind}-{ident}",
                    kind=kind,
                    url=f"mock://stock/{kind}/{ident}?q={query}",
                    download_url=f"mock://stock/{kind}/{ident}?q={query}",
                    thumbnail_url=None,
                    width=w,
                    height=h,
                    duration_seconds=8.0 if kind == "video" else None,
                    author="Mock Library",
                    source="mock",
                    license="Development placeholder - not for distribution",
                )
            )
        return items

    def download(self, item: StockMediaItem) -> tuple[bytes, str]:
        query = item.url.split("q=")[-1] if "q=" in item.url else item.id
        w, h = item.width or 1920, item.height or 1080
        if item.kind == "image":
            return render_placeholder(f"stock photo: {query}", w, h, label=f"Stock: {query}"), "image/png"
        res = MockVideoProvider().generate_video(f"stock footage: {query}", width=min(w, 1280), height=min(h, 720), duration_seconds=item.duration_seconds or 8.0)
        return res.data, res.content_type
