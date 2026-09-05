# THE NIGHT BEFORE — HOOK · Brand system + 7-asset record (OBLIK, 2026)

Product (from the author's final PDF): a morning-training adherence system.
A 10-minute night-before ritual — HOOK: Hang the clothes · Open the timer app ·
Order the if-then · Kodak: photo the hook. "Morning does not decide. Night
already did." Buyer: people who mean it at night and negotiate in the morning.
NOT a workout program, NOT motivation, NOT medical advice. No invented
testimonials, stats, or claims anywhere in these assets — every line is from
the PDF (implementation-intentions science attributed to Gollwitzer & Sheeran).

## Locked identity (identical across all 7)

- Palette: paper `#FAF8F4`, ink `#1C1917`, navy `#1E3A8A`, deep navy `#0D1833`,
  accent `#1D4ED8`, amber `#C97D1F` / light `#E8A33D`.
- Type: Fraunces (display serif) + Inter (text). `src/fonts/` holds the VFs.
- Motif: the night-before desk — wooden hook, hung kit, phone timer, notebook,
  warm lamp glow in navy shadow. `src/bg-*.png` (AI-generated, text-free).
- Footer lockup on TikToks: `THE NIGHT BEFORE — HOOK / OBLIK · on Gumroad`.

## Files

- `A1-cover.png` (1600×2560) — hero cover: title, tagline, photo, value prop,
  contents strip, honesty footer.
- `A2-gumroad-thumbnail.png` (1280×720) — grid-built, NOT a resize: giant title
  legible at 300px, one outcome line, photo slice right.
- `A3-tiktok-1-pain.png` (1080×1920) — "At night you mean it. In the morning
  you negotiate." + 3 pain lines, open loop, no solution.
- `A3-tiktok-2-reveal.png` — the HOOK 4 moves + ALSO INSIDE inventory box.
- `A3-tiktok-3-transformation.png` — BEFORE morning-meeting card vs AFTER
  one-decision card. Realistic, no hype.
- `A3-tiktok-4-difference.png` — "Okay. How, exactly?" + 5 not-Googleable
  items incl. cited 94-test meta-analysis.
- `A3-tiktok-5-showcase.png` — product hero + 3 points + Gumroad CTA button.
- `build_assets.py` — deterministic rebuild (Pillow + Fraunces/Inter VFs).
  Re-run after any copy change; visually QA before shipping.

## QA rules that were enforced (keep enforcing)

- Title/copy never clipped: auto-fit checks on cover strip + thumbnail lines.
- No tofu glyphs: ✕/✓/→/↓ verified in Inter/Fraunces; X marks are drawn.
- No box/footer collisions; no invented content — PDF is the only copy source.
