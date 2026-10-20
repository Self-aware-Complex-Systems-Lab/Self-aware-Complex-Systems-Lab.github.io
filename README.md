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

## Automatic updates

- **Publications**: `.github/workflows/update-publications.yml` runs every Monday (and on demand from the Actions tab).
  `scripts/update_publications.py` queries OpenAlex and Crossref by Prof. Sarkar's ORCID (plus verified OpenAlex author IDs, see below), appends genuinely new papers to
  `src/data/publications-added.json`, refreshes duplicate detection and each member's publication list, and commits.
  The deploy workflow then rebuilds the site. Requires *Settings → Actions → General → Workflow permissions: Read and write*.
  Tests (offline, no network): `python -m unittest discover -s scripts/tests -v`.

### Publication updater: sources, verified author IDs, failures

**Why ORCID alone is not enough.** OpenAlex splits one person into several author records. A record that has no ORCID
is invisible to the ORCID query. *Personalized Federated Direct Preference Optimization via LoRA Adapters* (arXiv 2610.12885)
was filed under `A5158521094`, a new record with no ORCID, so the ORCID query never returned it.

**Retrieval** (`src/data/publication-sources.json`): the updater takes the union of
(1) works whose authorship carries the PI's ORCID and (2) works of the IDs in `verifiedOpenAlexAuthorIds`. It
deduplicates by OpenAlex work ID, then applies the usual lookback, type filters and duplicate rules. Each new entry
records its route in `retrieval` (e.g. `["openalex-author:A5158521094"]`). Entries are only ever appended, so `added:<i>` keys stay valid.

A verified ID is a trust decision. Every work on that record is imported, with or without affiliation data, because
older OpenAlex records often lack affiliations. Affiliation is evidence for *verifying* a record, not a filter on its works.
For the same reason the updater never trusts a record because it is named "Soumik Sarkar" or lists Iowa State.
`A5101953320` shows why: it has a different ORCID and mixes the PI's Iowa State papers with another researcher's work.

**Adding another verified ID**
1. `python scripts/update_publications.py --review-candidates` lists same-name OpenAlex records that are not yet
   classified, with their latest works, co-authors and affiliation strings. It only reads.
2. Accept a record only when every work on it is the PI's: check the co-authors (lab members, known collaborators),
   the department (Mechanical Engineering / Translational AI Center, Iowa State), and the paper itself (arXiv/publisher author list).
3. Add `{"id", "verified", "reason", "evidence": [URLs]}` to `verifiedOpenAlexAuthorIds`. Records you looked at but did
   not accept go in `pendingReview` (undecided) or `doNotTrust` (mixed or different person). Neither list is ever queried.
4. Push to `main`. Changing the config triggers the updater.

Each weekly run also runs `--check-candidates`. It raises a GitHub Actions **warning** (shown on the run page; GitHub's
notification settings decide whether you are emailed) for any new same-name record affiliated with Iowa State that is
not ORCID-linked or listed in the config. That is how a paper like arXiv 2610.12885 gets noticed within a week. The check
only alerts: it never imports papers or edits the config, and its failure never fails the run. Move a record into
`pendingReview` to silence its warning while it is undecided.

**Failures and partial runs.** Requests retry 429, 5xx and timeouts up to 3 times, honouring `Retry-After` up to 2 minutes.
Each run writes a JSON summary (`--summary`, shown on the Actions run page) with every route's success, fetch count,
unique works, skipped and added entries, metadata outcome and errors:
- `ok`: all routes and the metadata refresh succeeded. Commit.
- `degraded`: publications were updated but the optional metrics/corresponding-author refresh failed. Those two files
  stay unchanged, the commit message says `[metadata refresh failed]`, and the run shows a warning.
- `partial` / `failed`: a publication route failed, or derived data could not be rebuilt. **Nothing is written**, not
  even additions from routes that worked, and the workflow fails without committing or deploying. The summary lists
  the withheld additions. Existing publications are never removed.

The commit message counts additions from the summary: `Auto-update publications (+N) …` when papers were added,
`Refresh publication metadata …` when only metadata changed. No commit is made when nothing changed.

**Limitations.** OpenAlex rejects keyless *cursor* paging past page 1 (HTTP 401), so the updater pages by page number
(up to 10,000 results). An optional `OPENALEX_API_KEY` environment variable is used if present but is not required.
Without a key, requests share a small free daily budget per IP; when it runs out, the run fails visibly and the next
weekly run retries. Papers that exist only on unverified or mixed records (see `pendingReview` / `doNotTrust`) are not
imported until someone reviews them. Citation metrics (`scholar-metrics.json`) come from the single largest ORCID-linked
record. They are *not* summed across fragmented records: h-index and i10 are not additive and the records share works.
They can therefore slightly undercount. Corresponding authors (`pub-meta.json`) come from OpenAlex's
`corresponding_author_ids` over the same work union as the publications, never from author order.
- **CV**: `/cv/` is generated from the site data, and `scripts/render-cv-pdf.mjs` prints it to `/cv/Soumik_Sarkar_CV.pdf`
  on every build, so the CV always matches the latest publications, grants and talks.
- **Featured papers / project links**: edit `src/data/featured-publications.json` and `src/data/publication-links.json`.

The site is self-contained: fonts, images and thumbnails are served from this repository (a test enforces this).

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
