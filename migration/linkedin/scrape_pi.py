"""Scrape Prof. Sarkar's LinkedIn profile + activity feed using joeyism/linkedin_scraper (v3).
Requires session.json from create_session.py. Low volume, single profile, polite pacing.
Output: migration/linkedin/profile.json, migration/linkedin/posts.json"""
import asyncio, json, sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from linkedin_scraper import BrowserManager, PersonScraper, CompanyPostsScraper

URL = "https://www.linkedin.com/in/soumik-sarkar-448b2619/"
HERE = Path(__file__).parent
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 100

class PersonActivityScraper(CompanyPostsScraper):
    """Same feed parser as company posts; a person's activity feed uses identical urn:li:activity markup."""
    def _build_posts_url(self, url: str) -> str:
        return url.rstrip("/") + "/recent-activity/all/"

def dump(o):
    if hasattr(o, "model_dump"): return o.model_dump(mode="json")
    if is_dataclass(o): return asdict(o)
    return o.__dict__ if hasattr(o, "__dict__") else str(o)

async def main():
    async with BrowserManager(headless=False, slow_mo=50) as browser:
        await browser.load_session(str(HERE / "session.json"))
        person = await PersonScraper(browser.page).scrape(URL)
        (HERE / "profile.json").write_text(json.dumps(dump(person), indent=1, default=str, ensure_ascii=False))
        print("profile saved:", getattr(person, "name", None))
        posts = await PersonActivityScraper(browser.page).scrape(URL, limit=LIMIT)
        (HERE / "posts.json").write_text(json.dumps([dump(p) for p in posts], indent=1, default=str, ensure_ascii=False))
        print(len(posts), "posts saved")

asyncio.run(main())
