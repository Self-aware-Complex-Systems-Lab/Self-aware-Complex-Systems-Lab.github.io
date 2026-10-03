# Migration status (resume point for the /loop)
Live: https://self-aware-complex-systems-lab.github.io/ (push to main deploys; user authorized pushes to this repo)
- [x] Phases 1–8 done: crawl, images (114/114 verified), content (0 discrepancies), Astro site, 53 Playwright tests, README, MIGRATION_REPORT.md
- [x] Owner requests: no migration wording on site, black header w/ original logo, comma authors, no New badges, 3 indep. students -> alumni (people-overrides.json), Souradeep re-sync
- [ ] PENDING background: TrAC site archive -> migration/related/trac-ai/ ; then add new SCSLab-relevant images/details (owner asked)
- [x] Current members GitHub/sites/interests on People cards (11 high-confidence; Manas, Yongyun medium -> not shown)
- [ ] LinkedIn: needs user to run `.venv/bin/python migration/linkedin/create_session.py` (manual login), then scrape_pi.py
- [x] Proofread profiles for all 73 (people-profiles.json, profiles/CHANGELOG.md); per-person lab publications; 30 duplicate pubs hidden; faulty links fixed; PI Talks & Videos (8)
- [x] CI: deploys verified green after @types/node fix (ALWAYS confirm `gh run list` success before saying 'live')
- [ ] PENDING: TrAC funding where Sarkar is PI/Co-PI -> migration/related/trac-ai/funding-sarkar.json, then add to PI page Research Funding
After each change: npm run build && npx playwright test && content_audit.py, commit, push.
