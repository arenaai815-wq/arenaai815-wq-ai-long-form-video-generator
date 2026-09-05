# THE NIGHT BEFORE — HOOK · OBLIK Canva-language assets (v2, current)

Product (from the author's final PDF): a morning-training adherence system.
HOOK = Hang the clothes · Open the timer app · Order the if-then · Kodak:
photo the hook. "Morning does not decide. Night already did." NOT a workout,
NOT motivation, NOT medical advice. Every line of copy is from the PDF —
no invented pages, bonuses, testimonials, stats, or earnings.

## Identity (matches the OBLIK product line, not an invented brand)

- Palette: terracotta `#B96A3B`, cream `#F4EDE1`, charcoal `#20211F`,
  light terracotta `#E8A46E` for dark-bg accents.
- Type: Anton (condensed display) + Archivo (labels/body) + Inter (✓/→ glyphs
  only — Archivo lacks U+2713; never trust an unverified glyph, QA everything).
- Devices: DIGITAL PDF pill, INSTANT DOWNLOAD rotated badge, OBLIK wordmark,
  charcoal bands with terracotta rules, GET IT ON GUMROAD CTA pills.
- Mockups: photoreal studio scenes with the REAL designed cover art warped
  onto blank book/tablet surfaces (`place_art` + numpy perspective) — never
  words floating over a photo.

## Files

- `A1-cover.png` (1600×2560) — terracotta studio hero, cover art on book,
  inside-page art on tablet, top bar, bottom title panel.
- `A2-gumroad-thumbnail.png` (1080×1080, square per Gumroad spec) —
  grid-built: products top, charcoal band with giant HOOK.
- `A3-tiktok-1-pain.png` — concrete studio: AT NIGHT YOU MEAN IT. /
  IN THE MORNING YOU NEGOTIATE. + 3 pain lines + CTA pill.
- `A3-tiktok-2-reveal.png` — cream flatlay: OPEN IT. USE IT TONIGHT. +
  cover art on book, live 20:00 timer UI on phone, inventory mini-band.
- `A3-tiktok-3-transformation.png` — BEFORE card vs AFTER panel, split design.
- `A3-tiktok-4-difference.png` — concrete: OKAY. HOW, EXACTLY? + 5 numbered
  items incl. cited 94-test meta-analysis.
- `A3-tiktok-5-showcase.png` — terracotta hero + badge + 3 points + CTA.
- `build_v2.py` — deterministic rebuild (Pillow + numpy + Anton/Archivo/Inter
  VFs in `src/fonts/`, scenes in `src/v2-*.png`). Re-run after copy changes;
  visually QA before shipping.

## Hard lessons baked in (do not regress)

1. Match the seller's existing product-line language FIRST (ask for photos/
   links of their other products); never invent a fresh brand unprompted.
2. Digital products must LOOK digital: real cover art on real mockups,
   DIGITAL PDF / INSTANT DOWNLOAD signals, device screens showing inside pages.
3. `Image.composite(a, b, mask)`: mask=255 takes `a`. Getting this backwards
   paints canvases black — verify brightness stats after compositing.
4. Warp quads must be verified against renders at zoom, then nudged.
   Type must never collide with composited art; keep bottom 25% of TikToks
   CTA-safe (platform UI covers it).
