"""Locate a TrueType font for captions/text overlays across environments."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


@lru_cache
def default_font_path() -> str | None:
    if settings.font_path and Path(settings.font_path).exists():
        return settings.font_path
    env = os.environ.get("FONT_PATH")
    if env and Path(env).exists():
        return env
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    # Pillow ships DejaVuSans as a fallback in some builds
    try:
        import PIL

        pil_font = Path(PIL.__file__).parent / "fonts" / "DejaVuSans.ttf"
        if pil_font.exists():
            return str(pil_font)
    except Exception:
        pass
    # Repo-bundled fallback
    bundled = Path(__file__).resolve().parents[3] / "infrastructure" / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
    if bundled.exists():
        return str(bundled)
    return None


def font_family_name() -> str:
    p = default_font_path()
    if not p:
        return "Sans"
    name = Path(p).stem
    if "DejaVu" in name:
        return "DejaVu Sans"
    if "Liberation" in name:
        return "Liberation Sans"
    if "Noto" in name:
        return "Noto Sans"
    return name
