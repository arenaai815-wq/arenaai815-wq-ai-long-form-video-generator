---
name: design
description: Use for any digital product design work — landing pages, web apps, dashboards, editors, pricing, onboarding, settings, mobile-web views. Enforces product taste, tokens, UX rules, and self-review checklist.
---

# Digital Product Design Skill

Use this skill whenever the user asks for UI, UX, layout, landing page, dashboard, component, design system, or "make it look good / premium / clean" work.

## 1. Taste principles (follow these over generic AI defaults)

1. **Clarity over decoration.** Every screen has one primary job. If you can't state it in one sentence, simplify.
2. **Hierarchy first.** Size, weight, spacing, and color guide the eye: headline → value → action. Never make everything bold, large, or accent-colored.
3. **Calm surfaces, one accent.** Neutral backgrounds (white / warm gray / near-black), one intentional accent. No rainbow UI.
4. **Real content, never lorem.** Use realistic product copy, names, numbers, empty states. Placeholder text is a design failure.
5. **Design the states.** Every feature needs: default, loading, empty, error, success, and disabled. If you only design the happy path, the work is incomplete.
6. **Desktop-first but responsive.** Must work at 1440px, 768px, and 375px. No horizontal scroll, no overlapping text.
7. **Feel premium through restraint.** Premium = consistent spacing, aligned edges, restrained color, good type, fast-feeling interactions. Not gradients + shadows + animations stacked together.

## 2. Hard constraints (never violate)

- Stack-agnostic by default. If repo has Next.js/Tailwind, use it. Otherwise use semantic HTML + the tokens in `tokens.css`.
- Fonts: use system stack or one grotesk + one serif/sans pairing max. Never mix 3+ families. Never use emojis as icons — use inline SVG / lucide-style icons.
- Colors: only tokens from `tokens.css`. Never invent new hex values inline.
- Banned AI-slop patterns:
  - purple/blue mesh gradients as hero background
  - glassmorphism cards on gradients everywhere
  - generic "Lorem ipsum" or 3 identical feature cards with heroicons
  - tiny 12px gray body text on white with poor contrast
  - excessive rounded-3xl + drop shadows on everything
  - autoplay carousels, splash screens, fake testimonials with stock names
- Accessibility: body text contrast ≥ 4.5:1, interactive targets ≥ 44px, visible focus rings, labels on all inputs, `alt` on images.

## 3. Product UX process (follow in order)

1. **Restate the job:** "User is ___ trying to ___ so that ___." If unclear, ask one clarifying question before building.
2. **Information architecture:** list the sections / nav / page structure in words first (5-10 lines). Get the flow right before pixels.
3. **Content-first wireframe:** headline, subcopy, CTAs, proof, and data — written out, not boxes.
4. **Build the real screen:** implement with real copy + tokens + responsive behavior.
5. **Add states + edge cases:** empty, loading skeleton, error, long text truncation, zero results.
6. **Self-review** against the checklist in section 6 before saying done.

## 4. Tokens (source of truth)

Always import/use `tokens.css`. Summary:

- `--bg`, `--surface`, `--surface-2` — page and card backgrounds
- `--ink`, `--ink-2`, `--ink-3` — primary / secondary / muted text
- `--line` — borders
- `--accent`, `--accent-ink`, `--accent-soft` — the ONE action color
- `--success`, `--warning`, `--danger` — status only, never decoration
- Type scale: 12 / 14 / 16 / 20 / 24 / 32 / 40 / 56. Body 15-16px, line-height 1.5-1.6.
- Spacing: 4px base (4, 8, 12, 16, 24, 32, 48, 64, 96).
- Radius: 8 (inputs), 12 (cards), 16 (modals/hero panels), 999 (pills).
- Shadows: only `shadow-sm` for cards, `shadow-md` for popovers/modals. No shadows on text.

For dark mode: invert bg/ink, keep the same accent hue, soften borders (see `tokens.css` `[data-theme="dark"]`).

## 5. Component patterns (copy these, don't reinvent)

- **Button:** primary = accent bg + white text, 44px height, 8px radius, medium weight. Secondary = transparent + border. Tertiary = text-only. One primary per view.
- **Input:** label above, 44px field, border `--line`, focus = 2px accent outline. Always include helper/error text slot.
- **Nav:** product name left, 3-5 links center/left, one primary CTA right. Sticky with blur only if content scrolls under it.
- **Hero (landing):** eyebrow → H1 (≤ 12 words) → subcopy (≤ 25 words) → 2 CTAs → proof row (logos / stats / screenshot). No full-viewport gradient blobs.
- **Card grid:** 3 cols desktop → 1 col mobile, equal heights, top-aligned icon/title, 24px padding, 1px border instead of heavy shadow.
- **Dashboard:** sidebar or top nav + page title + key metric row + main table/chart + side panel. Table needs empty + loading states.
- **Empty state:** icon + title + one-line explanation + one action. Never a blank page.
- **Pricing:** 2-3 tiers, highlight one, monthly/yearly toggle, feature list with checks, FAQ below.

## 6. Self-review checklist (must pass before finishing)

- [ ] Can I state the screen's one job in a sentence?
- [ ] Real copy everywhere (no lorem / "Card 1")?
- [ ] Visual hierarchy: one dominant headline, scannable body, clear CTA?
- [ ] Spacing consistent (4px grid), edges aligned, no orphan text?
- [ ] Responsive at 1440 / 768 / 375 with no overlap or h-scroll?
- [ ] All interactive elements have hover, focus, disabled, loading states?
- [ ] Contrast AA, labels on inputs, 44px targets?
- [ ] Only token colors/fonts used, one accent, restrained shadows?
- [ ] No banned slop patterns from section 2?

If any box fails, fix it before presenting.

## 7. How to present work

1. Start the dev server / preview and verify visually (never call it done from code alone).
2. Summarize: what you built, the user job, and key decisions (3-5 bullets).
3. Note anything you intentionally left out + what reference you'd like feedback on.
4. If the user says "feels off" in plain words (e.g. "too boxy"), translate to a token change (radius, spacing, type) and update this file's notes if it's a recurring preference.

## References

See `references/notes.md` — add 3-5 screenshots you love with a one-line "why". When in doubt, match those over inventing new styles.
