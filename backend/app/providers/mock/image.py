"""Mock image provider - renders a stylised, prompt-derived gradient poster as a real PNG."""

from __future__ import annotations

import hashlib
import io
import math
import random
import textwrap
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.providers.base import ImageProvider, ImageResult, UsageMetrics
from app.utils.fonts import default_font_path

PALETTES = [
    ((16, 24, 48), (72, 52, 212), (255, 128, 64)),
    ((10, 32, 30), (18, 140, 126), (250, 230, 120)),
    ((40, 10, 30), (200, 40, 90), (255, 200, 120)),
    ((18, 18, 18), (90, 90, 110), (240, 240, 250)),
    ((5, 30, 60), (0, 120, 200), (255, 255, 255)),
    ((45, 25, 5), (200, 120, 30), (255, 240, 200)),
    ((25, 5, 45), (120, 40, 200), (80, 220, 255)),
]


def render_placeholder(prompt: str, width: int, height: int, *, seed: int | None = None, label: str | None = None) -> bytes:
    rng = random.Random(seed if seed is not None else int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16))
    bg, mid, accent = rng.choice(PALETTES)

    # Work at reduced size for speed, then upscale (gradient + shapes upscale fine)
    scale = 4 if max(width, height) > 1200 else 2
    w, h = max(64, width // scale), max(64, height // scale)
    img = Image.new("RGB", (w, h), bg)
    px = img.load()
    angle = rng.uniform(0, math.pi)
    cx, cy = math.cos(angle), math.sin(angle)
    for y in range(h):
        for x in range(w):
            t = (x / w * cx + y / h * cy + 1) / 2
            t = max(0.0, min(1.0, t))
            px[x, y] = tuple(int(bg[i] * (1 - t) + mid[i] * t) for i in range(3))

    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(rng.randint(6, 14)):
        r = rng.randint(w // 12, w // 3)
        x, y = rng.randint(-r, w + r), rng.randint(-r, h + r)
        col = rng.choice([mid, accent]) + (rng.randint(30, 110),)
        if rng.random() < 0.5:
            draw.ellipse([x - r, y - r, x + r, y + r], fill=col)
        else:
            draw.polygon([(x, y - r), (x + r, y + r), (x - r, y + r)], fill=col)
    img = img.filter(ImageFilter.GaussianBlur(radius=max(1, w // 120)))
    img = img.resize((width, height), Image.LANCZOS)

    # Vignette + subtle film grain
    vignette = Image.new("L", (width, height), 0)
    vd = ImageDraw.Draw(vignette)
    vd.ellipse([-width * 0.25, -height * 0.25, width * 1.25, height * 1.25], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=width // 6))
    dark = Image.new("RGB", (width, height), (0, 0, 0))
    img = Image.composite(img, dark, vignette.point(lambda v: 60 + v * 195 // 255))

    draw = ImageDraw.Draw(img, "RGBA")
    font_path = default_font_path()
    title_size = max(24, height // 22)
    small_size = max(16, height // 45)
    try:
        title_font = ImageFont.truetype(font_path, title_size) if font_path else ImageFont.load_default()
        small_font = ImageFont.truetype(font_path, small_size) if font_path else ImageFont.load_default()
    except Exception:
        title_font = small_font = ImageFont.load_default()

    caption = (label or prompt or "AI visual").strip()
    # Keep the placeholder label compact and in the upper-middle band so it never collides
    # with burned-in captions (bottom) or on-screen text overlays (top-left / bottom-left).
    title_size = max(18, height // 34)
    try:
        title_font = ImageFont.truetype(font_path, title_size) if font_path else ImageFont.load_default()
    except Exception:
        title_font = ImageFont.load_default()
    max_text_w = int(width * 0.7)
    words, lines, cur = caption.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if draw.textlength(trial, font=title_font) <= max_text_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = lines[:2]
        lines[-1] = lines[-1].rstrip(".,;") + "…"
    lines = lines or textwrap.wrap(caption, 40)[:2]
    line_h = int(title_size * 1.3)
    text_h = len(lines) * line_h
    pad = title_size // 2
    box_w = max(int(draw.textlength(line, font=title_font)) for line in lines) + pad * 2
    x0 = (width - box_w) // 2
    y = int(height * 0.36) - text_h // 2
    draw.rounded_rectangle([x0, y - pad, x0 + box_w, y + text_h + pad], radius=pad, fill=(0, 0, 0, 90))
    for line in lines:
        tw = draw.textlength(line, font=title_font)
        draw.text(((width - tw) / 2 + 2, y + 2), line, font=title_font, fill=(0, 0, 0, 140))
        draw.text(((width - tw) / 2, y), line, font=title_font, fill=(255, 255, 255, 235))
        y += line_h
    tag = "MOCK PROVIDER • replace with IMAGE_PROVIDER=openai|stability|replicate"
    tw = draw.textlength(tag, font=small_font)
    draw.text((width - tw - width // 40, height // 40), tag, font=small_font, fill=(255, 255, 255, 120))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class MockImageProvider(ImageProvider):
    name = "mock"
    display_name = "Mock Image Generator (development)"
    is_mock = True
    model = "mock-image-v1"

    def capabilities(self) -> dict[str, Any]:
        return {"max_width": 3840, "max_height": 2160, "styles": ["any"], "negative_prompt": True, "seed": True}

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
    ) -> ImageResult:
        done = self._timer()
        label = prompt.split(",")[0][:90]
        data = render_placeholder(prompt, width, height, seed=seed, label=label)
        return ImageResult(
            data=data,
            content_type="image/png",
            width=width,
            height=height,
            seed=seed,
            provider_ref=None,
            usage=UsageMetrics(provider=self.name, model=self.model, images=1, latency_ms=done()),
        )
