"""One visit to the activity feed with the saved session; screenshot + whether real posts are present."""
import asyncio, sys
from pathlib import Path
from linkedin_scraper import BrowserManager
HERE = Path(__file__).parent
async def main():
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        await b.page.goto("https://www.linkedin.com/in/soumik-sarkar-448b2619/recent-activity/all/", wait_until="domcontentloaded")
        await b.page.wait_for_timeout(6000)
        print("url:", b.page.url)
        print("activity urns:", await b.page.evaluate("document.body.innerHTML.split('urn:li:activity:').length - 1"))
        print("visible text head:", (await b.page.evaluate("document.body.innerText"))[:600].replace("\n", " | "))
        await b.page.screenshot(path=sys.argv[1])
asyncio.run(main())
