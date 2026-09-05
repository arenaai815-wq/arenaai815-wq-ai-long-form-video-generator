---
name: design
description: Use for designing premium Gumroad digital products — PDF guides/playbooks, Notion templates, toolkits and bundles. Premium editorial + modern utility. Goal: "I would actually pay for this."
---

# Gumroad Digital Product Design Skill

Use this skill whenever the user asks for a digital product, guide, playbook, ebook, Notion template, toolkit, bundle, worksheets, checklists, or Gumroad listing assets.

NOT for websites or SaaS dashboards. The reference bar is premium Gumroad products — high-end Notion templates, professionally designed PDF guides, and complete toolkits — never generic AI PDFs or basic Canva docs.

## 1. Product types this skill covers

1. **Premium guides / playbooks (PDF):** magazine/book feel — strong cover, editorial typography, diagrams, callouts, checklists, beautiful page layouts.
2. **High-end Notion templates:** beautiful dashboard, custom icons, clear nav, interconnected sections, progress tracking, databases, cohesive identity.
3. **Professional toolkits / bundles:** complete package — main guide + worksheets + templates + checklists + swipe files + resources + quick-start + bonuses.

Most products combine all three: a guide + a Notion system + supporting files, sold as one bundle.

## 2. Design philosophy: premium editorial + modern utility

It must look like a professional design studio made it. That means:

- **Sophisticated typography** — one serif or distinctive grotesk for display, one clean sans for body. Never 3+ families. Never default Canva pairings.
- **Strong hierarchy** — every page: one clear headline, scannable sub-structure, generous whitespace. The eye always knows where to go first.
- **Consistent visual system** — same colors, same callout styles, same icon set, same header/footer, same chart style on every page. Consistency IS the premium signal.
- **Generous whitespace** — dense = cheap. Air = premium. Short paragraphs, wide margins, breathing room between sections.
- **Elegant section transitions** — chapter openers, divider pages, recurring motifs. The product should feel like chapters, not a long scroll.
- **Every page has a purpose** — no filler, no empty pages, no repeated "conclusion" fluff. If a page doesn't teach, help, or organize, cut it.
- **Clarity > decoration** — diagrams and callouts must earn their place. Decorative shapes, stock gradients, and icon confetti are banned (see section 9).

## 3. The "would I pay for this?" bar

Before calling anything done, it must pass this felt test:

- The **cover alone** looks worth the price in a Gumroad grid of competitors.
- The **first 5 pages** (cover → promise → what's inside → quick-start → first win) make the buyer feel smart for purchasing.
- A buyer **skimming in 60 seconds** still perceives completeness: TOC, tabs/dividers, checklists, worksheets, resources.
- A buyer **using it for real** finds things fast: numbered pages, running headers, TOC with page numbers, consistent section labels.
- Nothing looks AI-generated: no lorem ipsum, no generic stock copy, no repetitive layouts, no emotionless filler paragraphs.

## 4. Editorial system (source of truth — see tokens.css)

- **Page:** US Letter or A4, 18–22mm margins. One column for reading, two columns only for comparison/resource pages.
- **Type scale (print):** body 10–11pt / 15–17pt leading; H1 28–36pt chapter titles; H2 16–20pt section heads; H3 12–13pt bold small caps or labeled eyebrows; captions 8–9pt muted. Body line-length 55–70 characters.
- **Pairing default:** display serif (e.g. Fraunces / Playfair / Source Serif) + body sans (e.g. Inter / Source Sans / IBM Plex Sans) + mono for labels/data (e.g. IBM Plex Mono). Two families max plus mono for labels.
- **Color:** paper background (warm white), ink text, ONE brand accent + ONE deep shade of it for headers/dividers. Status colors (green/amber/red) only for trackers and checklists. No rainbow chapters.
- **Spacing rhythm:** 4px base on screen, 6pt baseline grid in print. Section gap ≥ 2× paragraph gap. Never trap headlines at page bottoms (keep-with-next).
- **Running system:** page numbers on every content page, running header with product short-title + chapter, consistent footer line. TOC page numbers must match the export.

## 5. PDF guide / playbook page system

Build every guide from these page types, in this order:

1. **Cover** — product title (≤ 7 words), one-line promise, audience line, edition/version, author mark. Must read clearly at Gumroad thumbnail size (title legible at 300px wide).
2. **Promise page** — who it's for / not for, what they'll walk away with (3–5 outcomes), how to use the product (10-minute quick-start path).
3. **Contents** — chapters with page numbers + toolkit map ("you also got: worksheets, Notion link, swipe files").
4. **Quick-start** — the fastest first win in 1–2 pages. This is the page that kills refunds.
5. **Chapters** — each opens with: chapter number + title + 2-line outcome + "in this chapter" box. Ends with: key takeaways + action checklist.
6. **Worksheets / action pages** — generous writing space (ruled or boxed), worked example already filled in, then a blank one. Never a worksheet with no example.
7. **Swipe files / templates** — copy-paste ready, clearly delimited, with usage notes ("replace [BRACKETS], keep the bold line").
8. **Resources + glossary** — curated links/tools with one-line "why", not link dumps.
9. **Bonus + next steps** — bonus clearly labeled as bonus, single CTA (review / share / upgrade), version + contact line.

Chapter length rule: no chapter longer than ~12 pages without a divider, checklist, or visual break.

## 6. Page component library (reuse, don't reinvent)

- **Callout box:** one style for Tip, one for Warning, one for Example. Icon + label + 1–3 lines. Same style every occurrence.
- **Checklist:** square boxes (print-friendly), grouped in 5–9 items, with a progress line ("7 steps — check as you go").
- **Steps:** numbered, verb-first titles ("Write the promise"), 2–4 lines each, outcome line at the end.
- **Worksheet:** title → worked example (filled, muted bg) → blank version (ruled space) → "done looks like" line.
- **Diagram:** one idea per figure, labeled parts, caption explaining the takeaway ("Fig 3 — the value loop: Teach → Tool → Proof"). Rebuild as clean vector/SVG-style, never pasted screenshots of text.
- **Table:** header row in deep accent shade, zebra rows subtle, left-aligned text, right-aligned numbers. No vertical gridlines.
- **Quote/proof:** large serif pull-line + source. Use sparingly (1–2 per guide) or it feels padded.
- **Section divider:** full-page or half-page, chapter number huge, title, outcome line, consistent motif. This is what makes flips feel premium.

## 7. Notion template system

Not a blank page with headers — a designed operating system:

- **Dashboard:** cover art + icon, one-line promise, 3–5 big-button nav (Start Here / Library / Tracker / Templates / Bonuses), progress bar linked to the tracker.
- **Navigation:** every sub-page links back to Dashboard. Breadcrumbs in the intro block. No orphan pages.
- **Icons:** one cohesive set (all outline or all filled, same source). Status icons consistent: ⬜ Not started / 🔵 In progress / ✅ Done — or a matching custom set.
- **Databases:** pre-built views (By Status / By Week / Gallery), 2–3 sample rows filled in so buyers see how it works, clear property names, one "Start here" template button per database.
- **Progress tracking:** checkbox or status rollups surfaced on the Dashboard. Buyer must SEE momentum.
- **Start Here page:** 5-minute setup (duplicate → set goal → first entry), Loom/script placeholder, FAQ (how to duplicate, reset, get help).
- **Visual identity:** cover images in one palette, callout colors mapped to meaning (blue = info, green = done, red = warning) consistently.

Deliverable format: share-link + setup PDF (1–2 pages) + version note. Test the duplicate flow fresh before shipping.

## 8. Toolkit / bundle packaging

The bundle must feel complete the second it's unzipped:

```
ProductName-v1/
  00-START-HERE.pdf (1 page: what's inside + 10-min path)
  01-Main-Guide.pdf
  02-Worksheets/ (print-ready, fillable where possible)
  03-Templates/ (Notion link + setup PDF, or Canva/DOC links)
  04-Checklists/ (1-page each, printable)
  05-Swipe-Files/ (copy-paste .md/.txt + usage notes)
  06-Resources/ (curated list, no dead links)
  07-Bonuses/ (clearly labeled BONUS-*)
  README.txt (same as START-HERE, plain text fallback)
```

Rules: `UPPERCASE-` numbered prefixes so sorting is automatic; every file opens with title + version + "part X of Y"; no "Untitled", no v1-final-FINAL naming; test the unzip on a clean folder.

## 9. Banned list (instant "looks cheap" signals)

- Generic Canva/ebook slop: purple-blue gradients, glassmorphism, confetti icons, fake signatures, stock-photo collages.
- Walls of 12px gray body text with no breaks, or the opposite: 40 pages of one quote per page.
- Inconsistent headings (3 heading styles on one spread), widows/orphans, headlines stranded at page bottoms.
- AI filler: "In today's fast-paced world…", "delve", repeated intros, 5 near-identical paragraphs, empty "conclusion" pages.
- Screenshots of text instead of rebuilt tables/diagrams; blurry or stretched images; watermarked assets.
- Notion pages with default gray titles, no icons/covers, empty databases with no sample rows, dead-end pages with no back-link.
- Gumroad thumbnails with tiny unreadable text, 6+ fonts, or before/after claims with no proof inside.

## 10. Gumroad listing assets

- **Thumbnail/cover:** legible at 300px, title ≤ 7 words, one visual motif from the guide, no tiny subtext. Export 1280×720 + 800×1000 variants.
- **Preview images (3–5):** cover → spread → worksheet → Notion dashboard → what's-inside map. Never show only the cover 5 times.
- **Mockups:** flat-lay or device frame in the product palette; keep shadows soft and consistent across all previews.
- **Description structure:** promise → who's it for/not for → what's inside (file list) → first-win preview → FAQ (format, tools needed, license, refunds, updates) → guarantee/version line.
- **Pricing perception:** anchor with the page count / file count / database count ("47 pages · 12 worksheets · Notion OS + bonuses"), launch price + Update policy ("free v1.x updates").

## 11. Build workflow (follow in order)

1. **Restate the product:** buyer, painful job, promised outcome, format (PDF length, Notion DBs, bundle contents). If unclear, ask before designing.
2. **Outline the TOC first** (chapters + page types from section 5 + bundle map from section 8). Lock scope before styling.
3. **Set the system:** pick the type pairing, accent, cover motif, callout/diagram styles. Show one sample spread + cover before building all pages.
4. **Build content + layout together** — real copy, real examples, no placeholders. Design the quick-start and one worksheet early; they're the value proof.
5. **Diagrams + Notion build** in the same visual language as the guide.
6. **QA + export:** preflight (fonts embedded, links work, TOC numbers match, images ≥150dpi), export print PDF + screen PDF, test unzip + Notion duplicate.
7. **Listing:** thumbnails, previews, description, file upload order, version stamp.

## 12. QA checklists (must pass before shipping)

**Guide:**
- [ ] Cover legible at thumbnail size; title/promise/audience present?
- [ ] TOC page numbers match export; running headers + folios correct?
- [ ] One type pairing, one accent, consistent callouts/diagrams throughout?
- [ ] Every chapter has opener + takeaways + action checklist?
- [ ] Worksheets have filled examples + blank space; tables/diagrams have captions?
- [ ] No widows/orphans, stranded headlines, blurry images, dead links?
- [ ] Fonts embedded, export ≥150dpi, file named `ProductName-v1-Guide.pdf`?

**Notion:**
- [ ] Dashboard → every section → back to Dashboard with no orphans?
- [ ] Icons/covers cohesive; sample rows + views present; progress visible?
- [ ] Start Here + duplicate test passed on a fresh account?

**Bundle + listing:**
- [ ] Unzip test clean; numbering/prefixes sort correctly; README matches?
- [ ] 3–5 distinct previews; description has file list + FAQ + version/update lines?
- [ ] "Would I pay for this?" — yes, at full price, not just launch discount?

If any box fails, fix it before presenting. Present with: what shipped (file list), the buyer job + first win, and what you left out.
