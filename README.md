# Self-aware Complex Systems Laboratory — website

Live site: https://self-aware-complex-systems-lab.github.io/

This is a static site built with [Astro](https://astro.build), TypeScript and Tailwind CSS. GitHub Pages deploys it automatically on every push to `main`.

## Updating content (no layout changes needed)

All text lives in `src/data/`:

| What | File |
|---|---|
| People (bio lines, links, photo path, category) | `people.json` |
| Moving someone between sections (e.g. to alumni), without touching the record | `people-overrides.json` |
| Extra profile links (homepage / Scholar / GitHub) | `people-web-links.json` |
| Links to hide (e.g. a link that belongs to someone else) | `link-corrections.json` |
| Publications | `publications.json` (main list), `publications-added.json` (newer entries) |
| PI page, research areas, home text | `page-principal-investigator.json`, `page-research.json`, `page-home.json` |
| Sponsor logos, gallery, research images | `assets.json` (files live in `public/assets/…`) |

**To add a person:**
1. Put the photo in `public/assets/team/<name>.jpg`.
2. Add an object to `people.json` with `name`, `category` (one of the section names used on the People/Alumni pages), `lines` (degrees and bio paragraphs, in order), `links` and `photo: "/assets/team/<name>.jpg"`.

**To add a publication:** add an object to `publications-added.json` with `category` (`journals` / `conferences` / `preprints`), `title`, `authors`, `venue`, `year` and `url`.

## Local development

```bash
npm ci
npm run dev        # http://localhost:4321
npm run check      # type check
npm run build      # production build in dist/
npx astro preview  # serve dist/
npx playwright test   # page, accessibility (axe), image, link, layout tests (desktop + mobile)
```

## Deployment

`.github/workflows/static.yml` runs `astro check` and `astro build` on every push to `main`, then deploys `dist/` to GitHub Pages.

One-time repository setting: **Settings → Pages → Build and deployment → Source: GitHub Actions** (already enabled). This is an organization Pages repo, so the site is served from the domain root and needs no `base` path.

## Migration archive (`migration/`)

This folder holds the record of how the site was migrated from the original Google Site. None of it is shown on the website.

- `MIGRATION_REPORT.md`: counts, method, limitations
- `page-inventory.json`, `archive/`: every original page (rendered HTML, text, screenshot) and every original image (`archive/images-raw/`, by SHA-256)
- `image-manifest.json`, `image-audit.json`, `manual-image-review.json`, `contact-sheets/`: per-image source → destination mapping and verification
- `content-audit.json`, `content-review.md`, `reports/`: text/link completeness and suspected errors in the original
- `scripts/run_all.sh`: re-sync from the Google Site, rebuild, and re-run both audits (needs `python3 -m venv .venv && .venv/bin/pip install playwright pillow imagehash beautifulsoup4 requests && .venv/bin/playwright install chromium`)
