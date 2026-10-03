#!/usr/bin/env bash
# Full re-sync from the original Google Site, then rebuild and re-audit.
# Usage: migration/scripts/run_all.sh [site-url-to-audit]   (default: local preview on :4321)
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
$PY migration/scripts/crawl.py            # Phase 1: inventory + snapshots
$PY migration/scripts/extract_pubs.py      # publications from the embed
$PY migration/scripts/recover_images.py    # Phase 2: images + manifest
$PY migration/scripts/label_assets.py      # visual labels for logos / group photos
$PY migration/scripts/build_site_data.py   # src/data/assets.json
$PY migration/scripts/extract_content.py   # Phase 3: people + page sections
npm run build
$PY migration/scripts/verify_images.py "${1:-http://localhost:4321}"   # Phase 5
$PY migration/scripts/content_audit.py     # Phase 6
