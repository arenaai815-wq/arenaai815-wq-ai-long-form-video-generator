"""Intro/outro/title cards and watermark images rendered with Pillow."""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.utils.fonts import default_font_path


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    p = default_font_path()
    try:
        return ImageFont.truetype(p, size) if p else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def render_text_card(out: Path, width: int, height: int, *, title: str, subtitle: str | None, seed: str = "") -> Path:
    """Dark cinematic gradient background (text itself is drawn by the ASS overlay layer)."""
    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))
    palettes = [((8, 10, 22), (34, 24, 78)), ((6, 20, 24), (10, 70, 80)), ((20, 8, 14), (90, 20, 50)), ((10, 10, 10), (40, 40, 50))]
    a, b = rng.choice(palettes)
    w, h = max(64, width // 8), max(64, height // 8)
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w * 0.6 + y / h * 0.4)
            px[x, y] = tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))
    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(5):
        r = rng.randint(w // 6, w // 2)
        x, y = rng.randint(0, w), rng.randint(0, h)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(b[0] + 40, b[1] + 40, b[2] + 60, 60))
    img = img.filter(ImageFilter.GaussianBlur(radius=max(2, w // 24))).resize((width, height), Image.LANCZOS)
    # subtle vignette
    vignette = Image.new("L", (width, height), 0)
    ImageDraw.Draw(vignette).ellipse([-width * 0.2, -height * 0.2, width * 1.2, height * 1.2], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=width // 5))
    img = Image.composite(img, Image.new("RGB", (width, height), (0, 0, 0)), vignette.point(lambda v: 70 + v * 185 // 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


def render_watermark(out: Path, text: str, font_size: int) -> Path:
    font = _font(font_size)
    dummy = Image.new("RGBA", (10, 10))
    bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0] + 24, bbox[3] - bbox[1] + 16
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, tw - 1, th - 1], radius=th // 4, fill=(0, 0, 0, 110))
    d.text((12 - bbox[0], 8 - bbox[1]), text, font=font, fill=(255, 255, 255, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out
