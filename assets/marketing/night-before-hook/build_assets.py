#!/usr/bin/env python3
"""Build the 7 marketing assets for THE NIGHT BEFORE - HOOK.
All copy is taken verbatim (or near-verbatim) from the author's PDF.
Style: warm premium editorial. Type: Fraunces (display) + Inter (text)."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
FONTS = os.path.join(SRC, "fonts")
OUT = HERE

PAPER = (250, 248, 244)
INK = (28, 25, 23)
MUTED = (87, 83, 78)
NAVY = (30, 58, 138)
DEEP = (13, 24, 51)      # near-black navy for dark panels
ACCENT = (29, 78, 216)
AMBER = (201, 125, 31)
AMBER_LT = (232, 163, 61)
LINE = (229, 222, 210)
SOFT = (219, 234, 254)

_font_cache = {}
def font(display: bool, size: int, weight: str = "Regular"):
    key = (display, size, weight)
    if key not in _font_cache:
        path = os.path.join(FONTS, "Fraunces-VF.ttf" if display else "Inter-VF.ttf")
        f = ImageFont.truetype(path, size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        _font_cache[key] = f
    return _font_cache[key]

def cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Crop-resize to fill w×h (center crop)."""
    s = max(w / img.width, h / img.height)
    nw, nh = int(img.width * s + 0.5), int(img.height * s + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - w) // 2
    y = (nh - h) // 2
    return img.crop((x, y, x + w, y + h))

def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_w: int):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines

def para(draw, xy, text, fnt, fill, max_w, lh, align="left"):
    x, y = xy
    for line in wrap(draw, text, fnt, max_w):
        w_ = draw.textlength(line, font=fnt)
        lx = x if align == "left" else x + (max_w - w_) / 2
        draw.text((lx, y), line, font=fnt, fill=fill)
        y += lh
    return y

def tracked(draw, xy, text, fnt, fill, tracking=0.22, align="left", max_w=None):
    """Draw uppercase eyebrow with letter tracking."""
    x, y = xy
    widths = [draw.textlength(c, font=fnt) for c in text]
    gap = fnt.size * tracking
    total = sum(widths) + gap * (len(text) - 1)
    if align == "center" and max_w is not None:
        x = x + (max_w - total) / 2
    cx = x
    for c, w_ in zip(text, widths):
        draw.text((cx, y), c, font=fnt, fill=fill)
        cx += w_ + gap
    return total

def tracked_width(draw, text, fnt, tracking=0.22):
    gap = fnt.size * tracking
    return sum(draw.textlength(c, font=fnt) for c in text) + gap * (len(text) - 1)

def tracked_fit(draw, xy, text, fill, max_w, size=26, weight="SemiBold", tracking=0.2, base="Inter"):
    s = size
    while s > 16:
        f = font(base == "Fraunces", s, weight)
        if tracked_width(draw, text, f, tracking) <= max_w:
            break
        s -= 1
    tracked(draw, xy, text, font(base == "Fraunces", s, weight), fill, tracking=tracking)
    return s

def scrim(img: Image.Image, top_alpha=0, bottom_alpha=200):
    """Vertical black gradient overlay for text legibility."""
    w_, h_ = img.size
    grad = Image.new("L", (1, h_))
    px = grad.load()
    for yy in range(h_):
        px[0, yy] = int(top_alpha + (bottom_alpha - top_alpha) * (yy / max(h_ - 1, 1)))
    mask = grad.resize((w_, h_))
    black = Image.new("RGB", (w_, h_), (5, 8, 18))
    return Image.composite(black, img, mask)

def rule(draw, x, y, w_, color, h=3):
    draw.rectangle([x, y, x + w_, y + h], fill=color)

def load_bg(name):
    return Image.open(os.path.join(SRC, name)).convert("RGB")

# ---------------------------------------------------------------- A1 COVER
def build_cover():
    W, H = 1600, 2560
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    M = 130  # margin
    # top brand bar
    tracked(d, (M, 110), "OBLIK  ·  THE NIGHT-BEFORE SYSTEM", font(False, 34, "SemiBold"), NAVY, tracking=0.28)
    rule(d, M, 170, W - 2 * M, LINE, 2)
    # title block
    y = 250
    d.text((M, y), "THE NIGHT", font=font(True, 168, "SemiBold"), fill=INK)
    y += 185
    d.text((M, y), "BEFORE", font=font(True, 168, "SemiBold"), fill=INK)
    y += 185
    f_hook = font(True, 168, "Black")
    d.text((M, y), "HOOK", font=f_hook, fill=NAVY)
    hw = d.textlength("HOOK", font=f_hook)
    d.text((M + hw + 30, y + 118), "— the 4-move evening ritual", font=font(False, 40, "Medium"), fill=MUTED)
    y += 200
    # tagline in italic serif
    d.text((M, y), "“Morning does not decide.", font=font(True, 64, "SemiBold"), fill=INK)
    y += 80
    d.text((M, y), "Night already did.”", font=font(True, 64, "SemiBold"), fill=INK)
    y += 120
    # photo window
    ph_h = 1010
    photo = cover_fit(load_bg("bg-hook-night.png"), W - 2 * M, ph_h)
    img.paste(photo, (M, y))
    d.rectangle([M, y, W - M, y + ph_h], outline=LINE, width=2)
    y += ph_h + 70
    # value prop
    y = para(d, (M, y), "A 10-minute evening ritual that removes the morning vote. Four moves, same order, every night — so tomorrow the only decision left is start the timer.", font(False, 44, "Regular"), INK, W - 2 * M, 62) + 45
    # contents strip (auto-fit to one line)
    strip = ["10 chapters", "If-then library", "Friction audit",
             "14-night log", "One-page card"]
    ss = 36
    f_ss = font(False, ss, "SemiBold")
    sep = " \u00b7 "
    total = sum(d.textlength(s, font=f_ss) for s in strip) + d.textlength(sep, font=f_ss) * (len(strip) - 1)
    while total > W - 2 * M - 30 and ss > 24:
        ss -= 2
        f_ss = font(False, ss, "SemiBold")
        total = sum(d.textlength(s, font=f_ss) for s in strip) + d.textlength(sep, font=f_ss) * (len(strip) - 1)
    sx = M
    for i, label in enumerate(strip):
        if i:
            d.text((sx, y), sep, font=f_ss, fill=AMBER)
            sx += d.textlength(sep, font=f_ss)
        d.text((sx, y), label, font=f_ss, fill=NAVY if not i else INK)
        sx += d.textlength(label, font=f_ss)
    y += 90
    rule(d, M, y, W - 2 * M, NAVY, 4)
    y += 30
    d.text((M, y), "Not a workout.  Not motivation.  The evening job.", font=font(False, 36, "Medium"), fill=MUTED)
    y += 60
    d.text((M, y), "OBLIK · 2026 · Personal use · Not medical advice", font=font(False, 30, "Regular"), fill=MUTED)
    img.save(os.path.join(OUT, "A1-cover.png"))
    print("A1 cover done")

# ---------------------------------------------------------------- A2 THUMB
def build_thumb():
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), DEEP)
    # right-side photo
    photo = cover_fit(load_bg("bg-hook-night.png"), 520, H)
    photo = scrim(photo, 60, 60)
    img.paste(photo, (W - 520, 0))
    # fade edge between text side and photo
    fade = Image.new("L", (160, H))
    fp = fade.load()
    for x in range(160):
        v = int(255 * (x / 159))
        for yy in range(H):
            fp[x, yy] = v
    img.paste(Image.new("RGB", (160, H), DEEP), (W - 520, 0), fade)
    d = ImageDraw.Draw(img)
    M = 70
    tracked_fit(d, (M, 64), "OBLIK · 10 MIN TONIGHT → ONE TAP TOMORROW", AMBER_LT,
                (W - 520) - M - 24, size=26, tracking=0.2)
    y = 120
    d.text((M, y), "THE NIGHT", font=font(True, 112, "SemiBold"), fill=PAPER)
    y += 128
    d.text((M, y), "BEFORE", font=font(True, 112, "SemiBold"), fill=PAPER)
    y += 128
    f_hook = font(True, 112, "Black")
    d.text((M, y), "HOOK", font=f_hook, fill=AMBER_LT)
    y += 150
    d.text((M, y), "Stop negotiating with morning-you.", font=font(False, 34, "Medium"), fill=PAPER)
    # amber rule
    rule(d, M, H - 56, 200, AMBER, 6)
    img.save(os.path.join(OUT, "A2-gumroad-thumbnail.png"))
    print("A2 thumb done")

# ---------------------------------------------------------------- helpers
def tiktok_base():
    W, H = 1080, 1920
    return Image.new("RGB", (W, H), PAPER), W, H

def brand_foot(d, W, H, dark=False):
    fill = PAPER if dark else MUTED
    sub = (200, 196, 188) if dark else MUTED
    d.text((72, H - 130), "THE NIGHT BEFORE — HOOK", font=font(False, 30, "SemiBold"), fill=fill)
    d.text((72, H - 88), "OBLIK · on Gumroad", font=font(False, 28, "Regular"), fill=sub)

# ------------------------------------------------------------- P1 PAIN
def build_p1():
    img, W, H = tiktok_base()
    photo = cover_fit(load_bg("bg-hand-hook.png"), W, 1050)
    photo = scrim(photo, 30, 230)
    img.paste(photo, (0, 0))
    d = ImageDraw.Draw(img)
    tracked(d, (72, 96), "DOES THIS SOUND FAMILIAR?", font(False, 30, "SemiBold"), AMBER_LT, tracking=0.24)
    d.text((72, 150), "At night,", font=font(True, 104, "SemiBold"), fill=PAPER)
    d.text((72, 262), "you mean it.", font=font(True, 104, "SemiBold"), fill=PAPER)
    d.text((72, 420), "In the morning,", font=font(True, 88, "Regular"), fill=PAPER)
    d.text((72, 520), "you negotiate.", font=font(True, 88, "Black"), fill=AMBER_LT)
    y = 1120
    pains = ["The clothes are in a drawer.",
             "The timer is in a folder.",
             "And the first 20 seconds win — again."]
    for p in pains:
        d.ellipse([72, y + 14, 96, y + 38], fill=AMBER)
        d.text((120, y), p, font=font(False, 40, "Medium"), fill=INK)
        y += 78
    y += 40
    box = [72, y, W - 72, y + 210]
    d.rounded_rectangle(box, radius=24, fill=NAVY)
    d.text((112, y + 30), "The problem is not motivation.", font=font(True, 44, "SemiBold"), fill=PAPER)
    d.text((112, y + 100), "It's the morning vote. Kill it the night before. →",
           font=font(False, 34, "Regular"), fill=(214, 222, 245))
    brand_foot(d, W, H)
    img.save(os.path.join(OUT, "A3-tiktok-1-pain.png"))
    print("P1 done")

# ------------------------------------------------------------- P2 REVEAL
def build_p2():
    img, W, H = tiktok_base()
    photo = cover_fit(load_bg("bg-flatlay.png"), W, 760)
    img.paste(photo, (0, 0))
    d = ImageDraw.Draw(img)
    y = 800
    tracked(d, (72, y), "INSIDE THE PDF — WHAT YOU GET", font(False, 30, "SemiBold"), NAVY, tracking=0.24)
    y += 60
    d.text((72, y), "Open it. Use it", font=font(True, 84, "SemiBold"), fill=INK)
    y += 100
    d.text((72, y), "tonight.", font=font(True, 84, "Black"), fill=NAVY)
    y += 130
    moves = [("H", "Hang the clothes.", "where your feet hit the floor"),
             ("O", "Open the timer app.", "page one — never a folder"),
             ("O", "Order the if-then.", "one written sentence"),
             ("K", "Kodak: photo the hook.", "or the ritual is incomplete")]
    for L, t, s in moves:
        d.ellipse([72, y + 4, 140, y + 72], fill=NAVY)
        fl = font(True, 40, "Black")
        tw = d.textlength(L, font=fl)
        d.text((106 - tw / 2, y + 12), L, font=fl, fill=PAPER)
        d.text((164, y), t, font=font(False, 40, "SemiBold"), fill=INK)
        d.text((164, y + 52), s, font=font(False, 32, "Regular"), fill=MUTED)
        y += 108
    y += 16
    also = "10 chapters · if-then library · friction audit · 3 worked nights · 14-night log · one-page card"
    af = font(False, 34, "Medium")
    alines = wrap(d, also, af, W - 72 - 72 - 80)
    box_h = 66 + len(alines) * 48 + 30
    box = [72, y, W - 72, y + box_h]
    d.rounded_rectangle(box, radius=24, outline=LINE, width=2, fill=(255, 255, 255))
    d.text((112, y + 26), "ALSO INSIDE", font=font(False, 28, "SemiBold"), fill=AMBER)
    para(d, (112, y + 66), also, af, INK, W - 72 - 72 - 80, 48)
    brand_foot(d, W, H)
    img.save(os.path.join(OUT, "A3-tiktok-2-reveal.png"))
    print("P2 done")

# ------------------------------------------------------------- P3 OUTCOME
def build_p3():
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    tracked(d, (72, 96), "BEFORE → AFTER · NO HYPE", font(False, 30, "SemiBold"), NAVY, tracking=0.24)
    d.text((72, 150), "Tomorrow,", font=font(True, 92, "SemiBold"), fill=INK)
    d.text((72, 252), "rehearsed.", font=font(True, 92, "Black"), fill=NAVY)
    # before card
    y = 420
    box = [72, y, W - 72, y + 560]
    d.rounded_rectangle(box, radius=28, fill=(235, 231, 224))
    d.text((120, y + 36), "BEFORE · the morning meeting", font=font(False, 30, "SemiBold"), fill=MUTED)
    by = y + 100
    for line in ["Clothes? Drawer. Hunt.", "Timer? Folder. Page three.",
                 "Workout? Decide now.", "Phone first. Sofa. Skip."]:
        cx, cy = 141, by + 24
        d.line([cx - 11, cy - 11, cx + 11, cy + 11], fill=(150, 60, 50), width=7)
        d.line([cx - 11, cy + 11, cx + 11, cy - 11], fill=(150, 60, 50), width=7)
        d.text((180, by), line, font=font(False, 40, "Regular"), fill=MUTED)
        by += 76
    y += 600
    # arrow
    d.text((72, y + 6), "↓", font=font(False, 54, "Bold"), fill=AMBER)
    d.text((140, y), "10 minutes tonight changes the guest list.",
           font=font(True, 40, "SemiBold"), fill=INK)
    y += 110
    # after card
    box2 = [72, y, W - 72, y + 545]
    d.rounded_rectangle(box2, radius=28, fill=NAVY)
    d.text((120, y + 36), "AFTER · one decision left", font=font(False, 30, "SemiBold"), fill=AMBER_LT)
    ay = y + 100
    aft = [("Kit on the hook.", "seen first, no drawer"),
           ("Timer on page one.", "first tap starts 20:00"),
           ("If-then written.", "“After I… I start the timer.”"),
           ("Hook photographed.", "proof for tomorrow-you")]
    for t, s in aft:
        d.text((120, ay), "✓", font=font(False, 40, "Bold"), fill=AMBER_LT)
        d.text((180, ay), t, font=font(False, 40, "SemiBold"), fill=PAPER)
        d.text((180, ay + 50), s, font=font(False, 32, "Regular"), fill=(214, 222, 245))
        ay += 104
    brand_foot(d, W, H)
    img.save(os.path.join(OUT, "A3-tiktok-3-transformation.png"))
    print("P3 done")

# ------------------------------------------------------------- P4 DIFFERENCE
def build_p4():
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), DEEP)
    d = ImageDraw.Draw(img)
    tracked(d, (72, 96), "WHY THIS ISN'T A FREE POST", font(False, 30, "SemiBold"), AMBER_LT, tracking=0.24)
    d.text((72, 150), "“Prepare the", font=font(True, 88, "Regular"), fill=PAPER)
    d.text((72, 250), "night before.”", font=font(True, 88, "Regular"), fill=PAPER)
    d.text((72, 368), "Okay. How, exactly?", font=font(True, 76, "Black"), fill=AMBER_LT)
    y = 540
    d.text((72, y), "Free posts stop there. This file gives you:", font=font(False, 36, "Regular"), fill=(214, 222, 245))
    y += 80
    items = [("A timed order", "10:00 on the clock — minute by minute, sit if you finish early."),
             ("A photo rule", "Kodak: no photo, ritual incomplete. Proof beats promises."),
             ("A log", "14 nights. Hook Y/N. S or M. Patterns you can't argue with."),
             ("Failure protocols", "Ritual yes + morning no? The cue is wrong — move it earlier."),
             ("The science, cited", "If-then plans beat vague goals — 94-test meta-analysis.")]
    for t, s in items:
        d.rounded_rectangle([72, y, W - 72, y + 178], radius=20, outline=(38, 56, 100), width=2)
        d.ellipse([104, y + 36, 128, y + 60], fill=AMBER)
        lines = wrap(d, t, font(False, 38, "SemiBold"), W - 280)
        d.text((148, y + 26), lines[0], font=font(False, 38, "SemiBold"), fill=PAPER)
        para(d, (148, y + 80), s, font(False, 31, "Regular"), (214, 222, 245), W - 280, 42)
        y += 202
    brand_foot(d, W, H, dark=True)
    img.save(os.path.join(OUT, "A3-tiktok-4-difference.png"))
    print("P4 done")

# ------------------------------------------------------------- P5 SHOWCASE
def build_p5():
    W, H = 1080, 1920
    photo = cover_fit(load_bg("bg-hook-night.png"), W, H)
    img = scrim(photo, 150, 235)
    d = ImageDraw.Draw(img)
    tracked(d, (72, 100), "OBLIK · THE NIGHT-BEFORE SYSTEM", font(False, 28, "SemiBold"), AMBER_LT, tracking=0.26)
    d.text((72, 155), "THE NIGHT", font=font(True, 128, "SemiBold"), fill=PAPER)
    d.text((72, 285), "BEFORE", font=font(True, 128, "SemiBold"), fill=PAPER)
    f_hook = font(True, 150, "Black")
    d.text((72, 415), "HOOK", font=f_hook, fill=AMBER_LT)
    y = 640
    d.text((72, y), "“Morning does not decide.", font=font(True, 52, "SemiBold"), fill=PAPER)
    d.text((72, y + 66), "Night already did.”", font=font(True, 52, "SemiBold"), fill=PAPER)
    y += 190
    points = ["The 4-move ritual, timed to 10:00",
              "If-then library + friction audit",
              "14-night log + one-page card"]
    for p in points:
        d.ellipse([72, y + 12, 98, y + 38], outline=AMBER_LT, width=3)
        d.text((86, y + 6), "✓", font=font(False, 30, "Bold"), fill=AMBER_LT)
        d.text((122, y), p, font=font(False, 38, "Medium"), fill=PAPER)
        y += 76
    y += 60
    # CTA button
    btn = [72, y, W - 72, y + 130]
    d.rounded_rectangle(btn, radius=65, fill=AMBER)
    ct = "Get it on Gumroad  →"
    cf = font(False, 44, "Bold")
    cw = d.textlength(ct, font=cf)
    d.text(((W - cw) / 2, y + 36), ct, font=cf, fill=(20, 16, 8))
    y += 170
    d.text((72, y), "Digital PDF · Personal use · Not medical advice",
           font=font(False, 30, "Regular"), fill=(214, 210, 200))
    img.save(os.path.join(OUT, "A3-tiktok-5-showcase.png"))
    print("P5 done")

if __name__ == "__main__":
    build_cover()
    build_thumb()
    build_p1()
    build_p2()
    build_p3()
    build_p4()
    build_p5()
    print("ALL 7 DONE")
