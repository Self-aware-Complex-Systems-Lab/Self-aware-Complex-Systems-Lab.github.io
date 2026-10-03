# Migration status (resume point for the /loop)
- [x] Phase 1 crawl: 6 pages (home, team-contact, principal-investigator, publications, research, media). Wayback CDX + nav agree; no sitemap. Snapshots in migration/archive/.
- [x] Publications: 384 parsed from embed (222 J / 83 C / 79 P) == source tirtho149/scs publications.json. src/data/publications.json
- [x] New pubs: 20 candidates (OpenAlex ORCID 0000-0002-6775-9199 + sarkar_papers/_works.json) in migration/publications-update/candidates.json — user asked to add these; dedupe-check then merge as "added after archive".
- [ ] Phase 2 image recovery (scripts/recover_images.py) — signed URLs, w1280 is max served size
- [ ] Phase 3 content → src/data/*.json (people from DOM blocks)
- [ ] Phase 4 Astro site
- [ ] Phase 5 image audit / Phase 6 content audit / Phase 7 tests+deploy prep / Phase 8 reports
Deploy target: NOT tirtho149/scs (that is the pubs data repo used by the live embed). Ask user before creating/pushing a new repo.
