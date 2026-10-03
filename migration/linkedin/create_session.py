"""Run ONCE yourself: opens a real browser window; log in to LinkedIn by hand.
The session cookie is saved to migration/linkedin/session.json (git-ignored, never committed)."""
import asyncio
from pathlib import Path
from linkedin_scraper import BrowserManager, wait_for_manual_login

async def main():
    async with BrowserManager(headless=False) as browser:
        await browser.page.goto("https://www.linkedin.com/login")
        print("Log in in the browser window (5 min timeout)...")
        await wait_for_manual_login(browser.page, timeout=300000)
        await browser.save_session(str(Path(__file__).with_name("session.json")))
        print("Session saved.")

asyncio.run(main())
