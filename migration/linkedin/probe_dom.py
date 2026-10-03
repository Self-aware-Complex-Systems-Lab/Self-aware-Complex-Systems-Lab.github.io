"""Find the DOM structure of a post card on a LinkedIn page (by a known text snippet)."""
import asyncio, sys
from pathlib import Path
from linkedin_scraper import BrowserManager
HERE = Path(__file__).parent
JS = r"""(snip) => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = w.nextNode())) if (n.textContent.includes(snip)) break;
  if (!n) return 'not found';
  const chain = []; let e = n.parentElement;
  for (let i = 0; e && i < 14; i++, e = e.parentElement) {
    const attrs = [...e.attributes].map(a => `${a.name}=${String(a.value).slice(0, 70)}`).join(' ');
    chain.push(`${e.tagName} ${attrs}`);
  }
  return chain.join('\n');
}"""
async def main(url, snip):
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        await b.page.goto(url, wait_until="domcontentloaded"); await b.page.wait_for_timeout(7000)
        print(await b.page.evaluate(JS, snip))
        print('links to posts:', await b.page.evaluate("[...new Set([...document.querySelectorAll('a[href*=\"/feed/update/\"], a[href*=\"/posts/\"]')].map(a=>a.href.split('?')[0]))].slice(0,8)"))
asyncio.run(main(sys.argv[1], sys.argv[2]))
