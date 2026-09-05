#!/usr/bin/env python3
"""V2 — OBLIK Canva-language assets for THE NIGHT BEFORE - HOOK.
Bold condensed type (Anton) + grotesk (Archivo) + photoreal mockups with the
REAL designed cover art composited onto blank book/tablet surfaces.
All copy from the author's PDF. Nothing invented."""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageStat

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
FONTS = os.path.join(SRC, "fonts")
OUT = HERE

CREAM = (244, 237, 225)
CREAM_DK = (232, 222, 203)
CHAR = (32, 33, 31)
TERRA = (185, 106, 59)
TERRA_DK = (148, 80, 44)
TERRA_LT = (232, 164, 110)
CONCRETE = (18, 18, 19)
MUTED_LT = (205, 198, 186)

_fc = {}
def F(fam, size, weight="Regular"):
    key = (fam, size, weight)
    if key not in _fc:
        path = {"anton": "Anton-Regular.ttf", "archivo": "Archivo-VF.ttf",
                "inter": "Inter-VF.ttf"}[fam]
        f = ImageFont.truetype(os.path.join(FONTS, path), size)
        if fam != "anton":
            try:
                f.set_variation_by_name(weight)
            except Exception:
                pass
        _fc[key] = f
    return _fc[key]

def cover_fit(img, w, h):
    s = max(w / img.width, h / img.height)
    nw, nh = int(img.width * s + 0.5), int(img.height * s + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))

def load_bg(n):
    return Image.open(os.path.join(SRC, n)).convert("RGB")

def wrap(d, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w_
    if cur:
        lines.append(cur)
    return lines

def para(d, xy, text, fnt, fill, max_w, lh, align="left"):
    x, y = xy
    for line in wrap(d, text, fnt, max_w):
        w_ = d.textlength(line, font=fnt)
        lx = x if align == "left" else x + (max_w - w_) / 2
        d.text((lx, y), line, font=fnt, fill=fill)
        y += lh
    return y

def tracked(d, xy, text, fnt, fill, tr=0.24):
    x, y = xy
    gap = fnt.size * tr
    for c in text:
        d.text((x, y), c, font=fnt, fill=fill)
        x += d.textlength(c, font=fnt) + gap

def tracked_w(d, text, fnt, tr=0.24):
    return sum(d.textlength(c, font=fnt) for c in text) + fnt.size * tr * (len(text) - 1)

def pill(d, xy, text, fnt, fg, bg, pad_x=28, pad_y=14):
    x, y = xy
    tw, th = d.textlength(text, font=fnt), fnt.size
    box = [x, y, x + tw + pad_x * 2, y + th + pad_y * 2]
    d.rounded_rectangle(box, radius=(th + pad_y * 2) // 2, fill=bg)
    d.text((x + pad_x, y + pad_y), text, font=fnt, fill=fg)
    return box

def badge(d, cx, cy, r, top, bottom, fg, bg, fnt, angle=-12):
    side = int(r * 2.4)
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    g = ImageDraw.Draw(layer)
    g.ellipse([8, 8, side - 8, side - 8], fill=bg + (255,))
    g.ellipse([22, 22, side - 22, side - 22], outline=fg + (255,), width=3)
    for i, line in enumerate([top, bottom]):
        w_ = g.textlength(line, font=fnt)
        g.text(((side - w_) / 2, side / 2 - fnt.size + i * (fnt.size + 8) - 6),
               line, font=fnt, fill=fg + (255,))
    layer = layer.rotate(angle, resample=Image.BICUBIC, expand=False)
    d._image.paste(layer, (int(cx - side / 2), int(cy - side / 2)), layer)

def find_coeffs(dst, src):
    m = []
    for (x1, y1), (x2, y2) in zip(dst, src):
        m.append([x1, y1, 1, 0, 0, 0, -x2 * x1, -x2 * y1])
        m.append([0, 0, 0, x1, y1, 1, -y2 * x1, -y2 * y1])
    A = np.array(m, float)
    B = np.array(src, float).reshape(8)
    return np.linalg.solve(A, B)

def place_art(base, art, quad, inset=0.05, shade=18):
    """Warp art onto quad [(x,y)x4 in fractions], with edge shade for realism."""
    W, H = base.size
    q = [(x * W, y * H) for x, y in quad]
    cx = sum(p[0] for p in q) / 4
    cy = sum(p[1] for p in q) / 4
    q2 = [(cx + (x - cx) * (1 - inset), cy + (y - cy) * (1 - inset)) for x, y in q]
    w = int(max(q2[1][0], q2[2][0]) - min(q2[0][0], q2[3][0]))
    h = int(max(q2[2][1], q2[3][1]) - min(q2[0][1], q2[1][1]))
    c = find_coeffs(q2, [(0, 0), (w, 0), (w, h), (0, h)])
    warped = art.resize((w, h), Image.LANCZOS).transform(
        base.size, Image.PERSPECTIVE, c.tolist(), Image.BICUBIC)
    mask = Image.new("L", (w, h), 255).transform(
        base.size, Image.PERSPECTIVE, c.tolist(), Image.BICUBIC)
    base.paste(warped, (0, 0), mask)
    return base

# ---------------------------------------------------------------- cover art
def cover_art(w=700, h=1000):
    img = Image.new("RGB", (w, h), CREAM)
    d = ImageDraw.Draw(img)
    m = 56
    d.rectangle([10, 10, w - 10, h - 10], outline=CHAR, width=4)
    tracked(d, (m, 44), "OBLIK", F("anton", 54), CHAR, tr=0.3)
    pill(d, (w - m - 300, 40), "DIGITAL PDF", F("archivo", 30, "Bold"), CREAM, TERRA)
    y = 150
    for line in ["THE NIGHT", "BEFORE"]:
        d.text((m, y), line, font=F("anton", 118), fill=CHAR)
        y += 122
    d.text((m, y), "HOOK", font=F("anton", 190), fill=TERRA)
    y += 205
    d.rectangle([m, y, w - m, y + 5], fill=CHAR)
    y += 24
    y = para(d, (m, y), "\u201cMorning does not decide. Night already did.\u201d",
             F("archivo", 36, "Medium"), CHAR, w - 2 * m, 48) + 26
    moves = [("H", "Hang the clothes"), ("O", "Open the timer app"),
             ("O", "Order the if-then"), ("K", "Kodak: photo the hook")]
    for L, t in moves:
        d.ellipse([m, y + 2, m + 52, y + 54], fill=CHAR)
        fl = F("anton", 34)
        tw = d.textlength(L, font=fl)
        d.text((m + 26 - tw / 2, y + 8), L, font=fl, fill=CREAM)
        d.text((m + 68, y + 4), t, font=F("archivo", 32, "SemiBold"), fill=CHAR)
        y += 66
    y += 14
    d.rectangle([m, y, w - m, y + 5], fill=TERRA)
    y += 22
    tracked(d, (m, y), "10 CHAPTERS \u00b7 14-NIGHT LOG \u00b7 ONE-PAGE CARD",
            F("archivo", 26, "Bold"), TERRA_DK, tr=0.12)
    return img

def page_art(w=640, h=1000):
    img = Image.new("RGB", (w, h), CREAM)
    d = ImageDraw.Draw(img)
    m = 52
    d.rectangle([8, 8, w - 8, h - 8], outline=CHAR, width=3)
    tracked(d, (m, 44), "HOOK \u2014 THE FOUR MOVES", F("archivo", 28, "Bold"), TERRA_DK, tr=0.14)
    y = 110
    d.text((m, y), "Same order.", font=F("anton", 64), fill=CHAR)
    y += 74
    d.text((m, y), "Every night.", font=F("anton", 64), fill=TERRA)
    y += 110
    rows = [("HANG", "Clothes where your feet hit the floor."),
            ("OPEN", "Timer app on page one. First tap starts 20:00."),
            ("ORDER", "One written if-then. \u201cAfter I\u2026 I start the timer.\u201d"),
            ("KODAK", "Photo the hook \u2014 or it didn\u2019t happen.")]
    for t, s in rows:
        d.rectangle([m, y, m + 150, y + 56], fill=CHAR)
        tw = d.textlength(t, font=F("anton", 34))
        d.text((m + 75 - tw / 2, y + 10), t, font=F("anton", 34), fill=CREAM)
        para(d, (m, y + 72), s, F("archivo", 29, "Regular"), CHAR, w - 2 * m, 40)
        y += 72 + 40 * len(wrap(d, s, F("archivo", 29, "Regular"), w - 2 * m)) + 26
    tracked(d, (m, h - 90), "OBLIK \u00b7 THE NIGHT BEFORE", F("archivo", 24, "Bold"), MUTED_LT if False else (120, 110, 95), tr=0.14)
    return img

COVER = cover_art()
PAGE = page_art()

# ---------------------------------------------------------------- quads
BOOK_Q = [(0.080, 0.330), (0.533, 0.344), (0.528, 0.725), (0.072, 0.712)]
TAB_Q = [(0.618, 0.415), (0.948, 0.422), (0.938, 0.702), (0.608, 0.693)]
FLAT_BOOK_Q = [(0.175, 0.165), (0.415, 0.165), (0.415, 0.615), (0.175, 0.615)]
FLAT_PHONE = (0.155, 0.695, 0.415, 0.915)  # x0,y0,x1,y1 fractions

def timer_ui(base, rect):
    W, H = base.size
    x0, y0, x1, y1 = (int(rect[0] * W), int(rect[1] * H), int(rect[2] * W), int(rect[3] * H))
    w_, h_ = x1 - x0, y1 - y0
    card = Image.new("RGB", (w_, h_), (12, 12, 13))
    g = ImageDraw.Draw(card)
    cx, cy, r = w_ // 2, h_ // 2 - 8, int(h_ * 0.30)
    g.ellipse([cx - r, cy - r, cx + r, cy + r], outline=TERRA_LT, width=max(4, h_ // 28))
    t = "20:00"
    f = F("archivo", int(h_ * 0.20), "Bold")
    tw = g.textlength(t, font=f)
    g.text(((w_ - tw) / 2, cy - f.size / 2 - 4), t, font=f, fill=CREAM)
    base.paste(card, (x0, y0))
    return base

# ---------------------------------------------------------------- A1 COVER
def build_a1():
    W, H = 1600, 2560
    scene = cover_fit(load_bg("v2-mock-terracotta.png"), W, H)
    # note: cover_fit crops sides on tall canvas; quads shift — recompute on crop
    sw, sh = load_bg("v2-mock-terracotta.png").size
    s = max(W / sw, H / sh)
    nw, nh = sw * s, sh * s
    ox, oy = (nw - W) / 2 / nw, (nh - H) / 2 / nh  # crop offset in src fractions
    def remap(q):
        return [((x - ox) * nw / W, (y - oy) * nh / H) for x, y in q]
    scene = place_art(scene, COVER, remap(BOOK_Q), inset=0.04)
    scene = place_art(scene, PAGE, remap(TAB_Q), inset=0.05)
    d = ImageDraw.Draw(scene)
    # top bar
    tracked(d, (80, 84), "OBLIK", F("anton", 56), CREAM, tr=0.3)
    pb = pill(d, (W - 80 - 330, 78), "DIGITAL PDF", F("archivo", 34, "Bold"), CREAM, TERRA)
    badge(d, W - 210, 470, 120, "INSTANT", "DOWNLOAD", CREAM, TERRA_DK, F("archivo", 30, "Bold"))
    # bottom scrim + type
    sc = Image.new("RGB", (W, 900), (24, 16, 10))
    scene.paste(sc, (0, H - 900))
    mask = Image.new("L", (1, 900))
    mp = mask.load()
    for yy in range(900):
        mp[0, yy] = int(235 * (yy / 899) ** 1.4)
    scene.paste(sc, (0, H - 900), mask.resize((W, 900)))
    d = ImageDraw.Draw(scene)
    y = H - 800
    d.text((80, y), "THE NIGHT", font=F("anton", 150), fill=CREAM)
    y += 158
    d.text((80, y), "BEFORE HOOK", font=F("anton", 150), fill=TERRA_LT)
    y += 185
    d.text((80, y), "Morning-you is not the one who decides.", font=F("archivo", 44, "Medium"), fill=CREAM)
    y += 90
    b = pill(d, (80, y), "GET IT ON GUMROAD  \u2192", F("archivo", 44, "Bold"), (20, 14, 8), TERRA_LT)
    d.text((80, b[3] + 30), "10-minute ritual \u00b7 If-then library \u00b7 14-night log \u00b7 One-page card",
           font=F("archivo", 34, "Regular"), fill=MUTED_LT)
    scene.save(os.path.join(OUT, "A1-cover.png"))
    print("A1 done")

# ---------------------------------------------------------------- A2 THUMB
def build_a2():
    S = 1080
    scene = load_bg("v2-mock-terracotta.png")
    # square crop around products (middle band)
    src0 = load_bg("v2-mock-terracotta.png")
    sw0, sh0 = src0.size
    top = int((sh0 - sw0) / 2) - 60
    scene = src0.crop((0, max(top, 0), sw0, max(top, 0) + sw0)).resize((S, S), Image.LANCZOS)
    t0 = max(top, 0)

    def rq(q):
        return [(x, (y * sh0 - t0) / sw0) for x, y in q]

    scene = place_art(scene, COVER, rq(BOOK_Q), inset=0.04)
    scene = place_art(scene, PAGE, rq(TAB_Q), inset=0.05)
    d = ImageDraw.Draw(scene)
    # bottom band
    band_h = 380
    d.rectangle([0, S - band_h, S, S], fill=CHAR)
    d.rectangle([0, S - band_h, S, S - band_h + 8], fill=TERRA)
    tracked(d, (54, S - band_h + 36), "OBLIK \u00b7 DIGITAL PDF", F("archivo", 30, "Bold"), TERRA_LT, tr=0.18)
    d.text((54, S - band_h + 84), "THE NIGHT BEFORE", font=F("anton", 96), fill=CREAM)
    f = F("anton", 150)
    d.text((54, S - band_h + 188), "HOOK", font=f, fill=TERRA_LT)
    hw = d.textlength("HOOK", font=f)
    d.text((54 + hw + 24, S - band_h + 258), "10 min tonight. One tap tomorrow.",
           font=F("archivo", 34, "Medium"), fill=CREAM)
    scene.save(os.path.join(OUT, "A2-gumroad-thumbnail.png"))
    print("A2 done")

# ---------------------------------------------------------------- P1 PAIN
def build_p1():
    W, H = 1080, 1920
    img = cover_fit(load_bg("v2-mock-concrete.png"), W, H)
    d = ImageDraw.Draw(img)
    pill(d, (72, 110), "OBLIK \u00b7 DIGITAL PDF", F("archivo", 30, "Bold"), CHAR, TERRA_LT)
    y = 260
    for line, col in [("AT NIGHT", CREAM), ("YOU MEAN IT.", CREAM),
                      ("IN THE MORNING", TERRA_LT), ("YOU NEGOTIATE.", TERRA_LT)]:
        d.text((72, y), line, font=F("anton", 118), fill=col)
        y += 128
    y += 30
    for p in ["The clothes are in a drawer.", "The timer is in a folder.",
              "And the first 20 seconds win \u2014 again."]:
        d.ellipse([72, y + 16, 72 + 26, y + 40], fill=TERRA)
        d.text((130, y), p, font=F("archivo", 42, "Medium"), fill=CREAM)
        y += 84
    y += 50
    b = pill(d, (72, y), "THE PROBLEM IS NOT MOTIVATION  \u2192", F("archivo", 38, "Bold"), (20, 14, 8), TERRA_LT)
    d.text((72, b[3] + 26), "It\u2019s the morning vote. Kill it the night before.",
           font=F("archivo", 36, "Regular"), fill=MUTED_LT)
    d.text((72, H - 110), "THE NIGHT BEFORE \u2014 HOOK \u00b7 OBLIK", font=F("archivo", 30, "Bold"), fill=MUTED_LT)
    img.save(os.path.join(OUT, "A3-tiktok-1-pain.png"))
    print("P1 done")

# ---------------------------------------------------------------- P2 REVEAL
def build_p2():
    W, H = 1080, 1920
    src0 = load_bg("v2-mock-flatlay.png")
    sw0, sh0 = src0.size
    cw = int(sh0 * (W / H))
    cx0 = 176
    img = src0.crop((cx0, 0, cx0 + cw, sh0)).resize((W, H), Image.LANCZOS)

    def rq(q):
        if isinstance(q[0], tuple):
            return [((x * sw0 - cx0) / cw, y) for x, y in q]
        x0, y0, x1, y1 = q
        return ((x0 * sw0 - cx0) / cw, y0, (x1 * sw0 - cx0) / cw, y1)

    img = place_art(img, COVER, rq(FLAT_BOOK_Q), inset=0.16)
    img = timer_ui(img, rq(FLAT_PHONE))
    d = ImageDraw.Draw(img)
    # top type block on cream space
    pill(d, (72, 64), "INSIDE THE PDF", F("archivo", 28, "Bold"), CREAM, CHAR)
    d.text((72, 140), "OPEN IT.", font=F("anton", 92), fill=CHAR)
    d.text((72, 232), "USE IT TONIGHT.", font=F("anton", 92), fill=TERRA)
    # bottom mini-band: inventory only, phone timer stays visible above it
    band_y = 1660
    d.rectangle([0, band_y, W, H], fill=CHAR)
    d.rectangle([0, band_y, W, band_y + 6], fill=TERRA)
    para(d, (72, band_y + 30), "H \u00b7 O \u00b7 O \u00b7 K \u2014 the 4-move ritual \u00b7 10 chapters \u00b7 if-then library \u00b7 friction audit \u00b7 14-night log \u00b7 one-page card",
         F("archivo", 32, "Regular"), CREAM, W - 144, 46)
    img.save(os.path.join(OUT, "A3-tiktok-2-reveal.png"))
    print("P2 done")

# ---------------------------------------------------------------- P3 OUTCOME
def build_p3():
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    pill(d, (72, 96), "BEFORE \u2192 AFTER \u00b7 NO HYPE", F("archivo", 30, "Bold"), CREAM, CHAR)
    d.text((72, 190), "TOMORROW,", font=F("anton", 118), fill=CHAR)
    d.text((72, 308), "REHEARSED.", font=F("anton", 118), fill=TERRA)
    y = 500
    d.rectangle([0, y, W, y + 560], fill=(233, 224, 205))
    d.text((72, y + 34), "BEFORE \u00b7 THE MORNING MEETING", font=F("archivo", 30, "Bold"), fill=(120, 100, 80))
    by = y + 100
    for line in ["Clothes? Drawer. Hunt.", "Timer? Folder. Page three.",
                 "Workout? Decide now.", "Phone first. Sofa. Skip."]:
        cx, cy = 104, by + 24
        d.line([cx - 12, cy - 12, cx + 12, cy + 12], fill=(150, 60, 50), width=8)
        d.line([cx - 12, cy + 12, cx + 12, cy - 12], fill=(150, 60, 50), width=8)
        d.text((150, by), line, font=F("archivo", 42, "Medium"), fill=CHAR)
        by += 84
    y += 600
    d.text((72, y), "10 MINUTES TONIGHT.", font=F("anton", 64), fill=CHAR)
    y += 100
    d.rectangle([0, y, W, H], fill=TERRA)
    y += 40
    d.text((72, y), "AFTER \u00b7 ONE DECISION LEFT", font=F("archivo", 30, "Bold"), fill=CREAM)
    ay = y + 66
    for t, s in [("Kit on the hook.", "seen first, no drawer"),
                 ("Timer on page one.", "first tap starts 20:00"),
                 ("If-then written.", "\u201cAfter I\u2026 I start the timer.\u201d"),
                 ("Hook photographed.", "proof for tomorrow-you")]:
        r = 20
        d.ellipse([72, ay + 6, 72 + 44, ay + 50], fill=CREAM)
        cf = F("inter", 34, "Bold")
        ck = "\u2713"
        d.text((72 + 22 - d.textlength(ck, font=cf) / 2, ay + 8), ck, font=cf, fill=TERRA)
        d.text((140, ay), t, font=F("archivo", 42, "Bold"), fill=CREAM)
        d.text((140, ay + 54), s, font=F("archivo", 34, "Regular"), fill=CREAM)
        ay += 118
    d.text((72, H - 110), "THE NIGHT BEFORE \u2014 HOOK \u00b7 OBLIK", font=F("archivo", 30, "Bold"), fill=CREAM)
    img.save(os.path.join(OUT, "A3-tiktok-3-transformation.png"))
    print("P3 done")

# ---------------------------------------------------------------- P4 DIFFER
def build_p4():
    W, H = 1080, 1920
    img = cover_fit(load_bg("v2-mock-concrete.png"), W, H)
    d = ImageDraw.Draw(img)
    pill(d, (72, 110), "WHY THIS ISN\u2019T A FREE POST", F("archivo", 30, "Bold"), CHAR, TERRA_LT)
    y = 230
    y = para(d, (72, y), "\u201cPrepare the night before.\u201d", F("anton", 92), CREAM, W - 144, 100) + 10
    d.text((72, y), "OKAY. HOW, EXACTLY?", font=F("anton", 76), fill=TERRA_LT)
    y += 120
    items = [("TIMED ORDER", "10:00 on the clock \u2014 minute by minute."),
             ("PHOTO RULE", "Kodak: no photo, ritual incomplete."),
             ("THE LOG", "14 nights. Hook Y/N. S or M."),
             ("FAILURE PROTOCOLS", "Ritual yes + morning no? Move the cue earlier."),
             ("CITED SCIENCE", "If-then plans beat vague goals \u2014 94-test meta-analysis.")]
    for i, (t, s) in enumerate(items):
        d.rectangle([72, y, W - 72, y + 172], outline=(90, 70, 55), width=2)
        d.text((104, y + 22), f"0{i + 1}", font=F("anton", 40), fill=TERRA_LT)
        d.text((200, y + 22), t, font=F("archivo", 36, "Bold"), fill=CREAM)
        para(d, (200, y + 72), s, F("archivo", 32, "Regular"), MUTED_LT, W - 272, 42)
        y += 196
    d.text((72, H - 110), "THE NIGHT BEFORE \u2014 HOOK \u00b7 OBLIK", font=F("archivo", 30, "Bold"), fill=MUTED_LT)
    img.save(os.path.join(OUT, "A3-tiktok-4-difference.png"))
    print("P4 done")

# ---------------------------------------------------------------- P5 SHOW
def build_p5():
    W, H = 1080, 1920
    scene = load_bg("v2-mock-terracotta.png")
    scene = cover_fit(scene, W, H)
    sw, sh = load_bg("v2-mock-terracotta.png").size
    s = max(W / sw, H / sh)
    nw, nh = sw * s, sh * s
    ox, oy = (nw - W) / 2 / nw, (nh - H) / 2 / nh
    def remap(q):
        return [((x - ox) * nw / W, (y - oy) * nh / H) for x, y in q]
    scene = place_art(scene, COVER, remap(BOOK_Q), inset=0.04)
    scene = place_art(scene, PAGE, remap(TAB_Q), inset=0.05)
    d = ImageDraw.Draw(scene)
    badge(d, W - 200, 300, 115, "INSTANT", "DOWNLOAD", CREAM, TERRA_DK, F("archivo", 30, "Bold"))
    # lower third panel
    py = 1180
    d.rectangle([0, py, W, H], fill=CHAR)
    d.rectangle([0, py, W, py + 8], fill=TERRA)
    y = py + 50
    d.text((72, y), "THE NIGHT BEFORE", font=F("anton", 92), fill=CREAM)
    y += 100
    d.text((72, y), "HOOK", font=F("anton", 150), fill=TERRA_LT)
    y += 165
    for p in ["4-move ritual, timed to 10:00", "If-then library + friction audit", "14-night log + one-page card"]:
        d.text((72, y), "\u2713", font=F("inter", 38, "Bold"), fill=TERRA_LT)
        d.text((130, y), p, font=F("archivo", 38, "Medium"), fill=CREAM)
        y += 70
    y += 30
    pill(d, (72, y), "GET IT ON GUMROAD  \u2192", F("archivo", 44, "Bold"), (20, 14, 8), TERRA_LT)
    scene.save(os.path.join(OUT, "A3-tiktok-5-showcase.png"))
    print("P5 done")

if __name__ == "__main__":
    build_a1(); build_a2(); build_p1(); build_p2(); build_p3(); build_p4(); build_p5()
    print("ALL 7 V2 DONE")
