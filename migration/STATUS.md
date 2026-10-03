# Migration status (resume point for the /loop)
Live: https://self-aware-complex-systems-lab.github.io/ (push to main deploys; user authorized pushes to this repo)
- [x] Phases 1–8 done: crawl, images (114/114 verified), content (0 discrepancies), Astro site, 53 Playwright tests, README, MIGRATION_REPORT.md
- [x] Owner requests: no migration wording on site, black header w/ original logo, comma authors, no New badges, 3 indep. students -> alumni (people-overrides.json), Souradeep re-sync
- [x] Current members GitHub/sites/interests on People cards (11 high-confidence; Manas, Yongyun medium -> not shown)
- [ ] LinkedIn: needs user to run `.venv/bin/python migration/linkedin/create_session.py` (manual login), then scrape_pi.py
- [x] Proofread profiles for all 73 (people-profiles.json, profiles/CHANGELOG.md); per-person lab publications; 30 duplicate pubs hidden; faulty links fixed; PI Talks & Videos (8)
- [x] CI: deploys verified green after @types/node fix (ALWAYS confirm `gh run list` success before saying 'live')
- [x] TrAC archived (300 pages/181 imgs, local only); recent grants on PI page; featured pubs on home; Hsin-Jung & Mahsa -> alumni
- [x] Project pages/code (33 high-conf) on Publications + featured; CV page+PDF auto-built; weekly OpenAlex/Crossref updater (green); fonts self-hosted, 0 external runtime requests (tested)
- [ ] ASK USER: confirm repo Settings → Actions → Workflow permissions = Read and write (needed for updater to commit)
- [ ] ASK USER: purge 160MB TrAC files from git history (force-push) — not done
After each change: npm run build && npx playwright test && content_audit.py, commit, push.
