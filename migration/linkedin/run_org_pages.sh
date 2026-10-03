#!/usr/bin/env bash
# Scrape the TrAC, AIIRA and COALESCE LinkedIn company pages (posts + images), one after another, politely.
set -u
cd "$(dirname "$0")/../.."
for slug in traciastate aiira coalesceiastate; do
  .venv/bin/python -u migration/linkedin/scrape_activity.py 250 "https://www.linkedin.com/company/$slug/posts/?feedView=all" "org-$slug.json"
  .venv/bin/python -u migration/linkedin/capture_post_images.py "org-$slug.json" "org-$slug-images.json"
  sleep 20
done
echo ORG_DONE
