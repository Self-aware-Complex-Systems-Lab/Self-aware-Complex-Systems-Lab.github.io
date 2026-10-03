"""Open one LinkedIn URL with the saved session; report post markup counts and save a screenshot."""
import asyncio, sys
from pathlib import Path
from linkedin_scraper import BrowserManager
HERE = Path(__file__).parent
async def main(url, shot):
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        await b.page.goto(url, wait_until="domcontentloaded"); await b.page.wait_for_timeout(7000)
        await b.page.evaluate("window.scrollBy(0, 1500)"); await b.page.wait_for_timeout(3000)
        print("url:", b.page.url)
        print(await b.page.evaluate("""() => ({activityUrn: document.querySelectorAll('[data-urn^="urn:li:activity:"]').length,
            anyDataUrn: [...new Set([...document.querySelectorAll('[data-urn]')].map(e => e.getAttribute('data-urn').split(':').slice(0,3).join(':')))],
            dataId: document.querySelectorAll('[data-id^="urn:li:activity:"]').length,
            feedUpdates: document.querySelectorAll('.feed-shared-update-v2').length,
            htmlUrns: document.body.innerHTML.split('urn:li:activity:').length - 1})"""))
        await b.page.screenshot(path=shot)
asyncio.run(main(sys.argv[1], sys.argv[2]))
