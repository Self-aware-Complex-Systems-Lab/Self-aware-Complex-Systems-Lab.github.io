# SCSLab website migration report

Source: https://sites.google.com/view/scslab-isu/home (Google Sites), crawled and re-synced 2026-10-03.
Target: https://self-aware-complex-systems-lab.github.io/ (Astro + TypeScript + Tailwind on GitHub Pages).

Every number below comes from a file in `migration/`. Re-run `migration/scripts/run_all.sh` to regenerate them.

## Summary

| Metric | Value | Evidence |
|---|---|---|
| Original pages discovered | **6** (Home, Principal Investigator, Team & Contact, Research, Publications, Media) | `page-inventory.json` |
| Pages archived (rendered HTML, text, full-page screenshot) | **6 / 6** | `archive/<page>/` |
| Image occurrences discovered (img + CSS backgrounds, incl. header logo copies) | **114** | `image-manifest.json` |
| Unique original images (by SHA-256) | **103** | same |
| Images downloaded | **114 / 114 occurrences → 103 files** | same |
| Images verified | **114 / 114** (95 automated, 10 after manual visual review, 9 by byte identity only because they are not visibly rendered on the original: header logo copies and hidden carousel slides) | `image-audit.json`, `manual-image-review.json`, `contact-sheets/` |
| Unresolved / inaccessible images | **0** | `reports/unverified-images.md` |
| People migrated | **73**: PI 1, postdoc 1, doctoral 13, master's 3, independent study 4, postdoc alumni 4, graduate alumni 30, undergraduate alumni 17 | `src/data/people.json` |
| People with original photo correctly attached | **73 / 73** | image audit check 8/8b/10b; test `every person is rendered with their own photo` |
| Publications migrated | **384** from the original list (222 journal / 83 conference / 79 preprint), the same set as its source `tirtho149/scs/publications.json` | `src/data/publications.json` |
| Publications added (newer than the original list) | **20** (OpenAlex, ORCID 0000-0002-6775-9199, plus the local `sarkar_papers` scrape) | `src/data/publications-added.json`, `publications-update/` |
| Research funding entries / amounts preserved | 28 grants / **29 / 29** dollar amounts | `content-audit.json` |
| Original external links | **39**, all preserved except 2 hidden on purpose because they point to the wrong person | `content-audit.json`, `content-review.md` |
| Unresolved links | **0** broken internal links; 0 missing original links | `content-audit.json`, Playwright tests |
| Content discrepancies (original text block missing on the new site) | **0** (2 intentional omissions: "N/A" contact placeholders and the empty Media page's "Coming Soon") | `reports/content-discrepancies.md` |
| Automated tests | **53 passed**, 1 skipped (mobile-menu test on desktop) | `tests/site.spec.ts` |

## How images were recovered and verified
1. **Discovery:** Playwright rendered each page, scrolled it progressively, and collected every `<img>` and every computed CSS `background-image`. That covers lazy-loaded images, hidden carousel slides and header logos.
2. **Association:** each image's DOM block is the largest ancestor that contains exactly one content image. The person or section name comes from that block's own heading or first text line, and the category comes from the nearest preceding `<h2>`. Nothing is assigned by file order.
3. **Bytes:** for each image, the bytes the browser received (response interception) and a separate HTTP re-download were both SHA-256 hashed. All 114 pairs are identical.
4. **Audit (`scripts/verify_images.py`):**
   - Google re-signs image URLs on every load, so the audit reloads the original page and re-downloads the image at the same DOM position. Its SHA-256 must equal the local file (111/111 matched; the 3 CSS-background slides were checked by bytes).
   - The person's name is re-read from that block.
   - The audit takes an element screenshot of the image as rendered on the original and compares its perceptual hash with the local file.
   - It then loads the new site and confirms the image loads inside the right person card or section.
5. **Manual review:** the 10 images whose rendered crop differed (transparent logos, a header overlapping a diagram, tiny mobile-header logo copies) were checked side by side. The decisions are recorded in `manual-image-review.json`.

## Known limitations
- **Resolution cap:** Google Sites serves only signed, size-specific URLs. Every other size suffix (`=s0`, `=w16383`, `=d`, none) returns 403. **14 unique images** were served at exactly 1280 px wide, and the original uploads may have been larger. No higher-resolution public source exists, and nothing was upscaled.
- **Sponsor logos and group photos** have no alt text or caption in the original. They were identified by looking at them (`label_assets.py`). The sponsor names are certain; the group-photo captions are descriptive, not original.
- **Statuses are as listed on 2026-10-03.** Roles, employers and "currently" statements are reproduced as the original showed them. Web search suggests several are out of date (see `content-review.md`). The PI's funding list is historical.
- **Typos and inconsistencies** are kept verbatim and listed in `content-review.md`.
- **Owner-requested presentation changes:**
  - No "migrated from" wording appears on the site.
  - "N/A" contacts are hidden.
  - The empty Media page is replaced by the Gallery.
  - Three independent-study students were moved to alumni (`src/data/people-overrides.json`).
  - Authors are shown comma-separated.
- **Added links:** 72 high-confidence profile links (homepages, Scholar, GitHub) found by web search were added next to the original links. Evidence for each is in `people-web-search.json`.
- **Publications** in the original list carry citation counts from June 2026. The 20 added entries have none.
- **LinkedIn** posts are not included. LinkedIn blocks unauthenticated access (HTTP 999), so it needs a manual login first (`migration/linkedin/`).
