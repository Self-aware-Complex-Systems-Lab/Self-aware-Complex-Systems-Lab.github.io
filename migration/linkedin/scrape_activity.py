"""Collect Prof. Sarkar's LinkedIn activity feed (his posts and reposts) with the owner's saved session.

Slow, single-profile, capped. For each feed item: activity id, exact timestamp (decoded from the id), whether it is an
original post or a repost (and of whom), full text (after expanding "...more"), outbound links, linked article card,
image URLs, and the public post URL.

    .venv/bin/python migration/linkedin/scrape_activity.py [max_posts=150]
Output: migration/linkedin/posts.json
"""
import asyncio, datetime as dt, json, sys
from pathlib import Path
from linkedin_scraper import BrowserManager

HERE = Path(__file__).parent
# usage: scrape_activity.py [max_posts=150] [feed_url] [out_name=posts.json]
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 150
FEED = sys.argv[2] if len(sys.argv) > 2 else "https://www.linkedin.com/in/soumik-sarkar-448b2619/recent-activity/all/"
OUTNAME = sys.argv[3] if len(sys.argv) > 3 else "posts.json"

EXTRACT = r"""() => {
  const items = [];
  document.querySelectorAll('div[data-urn^="urn:li:activity:"]').forEach(el => {
    const urn = el.getAttribute('data-urn');
    const header = el.querySelector('.update-components-header__text-view, .update-components-header');
    const actor = el.querySelector('.update-components-actor__title, .update-components-actor__name');
    const textEl = el.querySelector('.update-components-text, .feed-shared-update-v2__description, .feed-shared-text');
    const article = el.querySelector('.update-components-article, .feed-shared-article');
    const links = [...(textEl ? textEl.querySelectorAll('a[href]') : [])].map(a => ({text: a.innerText.trim(), href: a.href}));
    const imgs = [...el.querySelectorAll('.update-components-image img, .feed-shared-image img, .update-components-article__image img, img.ivm-view-attr__img--centered')]
      .map(i => i.currentSrc || i.src).filter(s => s && s.startsWith('http') && !s.includes('profile-displayphoto'));
    items.push({
      urn,
      header: header ? header.innerText.trim().replace(/\s+/g, ' ') : null,
      actor: actor ? actor.innerText.trim().split('\n')[0] : null,
      text: textEl ? textEl.innerText.trim() : '',
      links,
      article: article ? {title: (article.querySelector('.update-components-article__title, .feed-shared-article__title') || {}).innerText || null,
                          href: (article.querySelector('a[href]') || {}).href || null} : null,
      images: [...new Set(imgs)],
    });
  });
  return items;
}"""

EXPAND = r"""() => { let n = 0; document.querySelectorAll('button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label*="see more" i]')
  .forEach(b => { if (b.innerText.toLowerCase().includes('more')) { b.click(); n++; } }); return n; }"""


def ts_from_urn(urn):
    """LinkedIn activity ids carry a millisecond timestamp in their top 41 bits."""
    try:
        i = int(urn.rsplit(":", 1)[1])
        return dt.datetime.fromtimestamp((i >> 22) / 1000, dt.timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


async def main():
    seen = {}
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        p = b.page
        await p.goto(FEED, wait_until="domcontentloaded")
        await p.wait_for_timeout(5000)
        if "/login" in p.url or "authwall" in p.url or "checkpoint" in p.url:
            print("NOT LOGGED IN:", p.url); return
        stale = 0
        while len(seen) < LIMIT and stale < 4:
            await p.evaluate(EXPAND)
            await p.wait_for_timeout(800)
            before = len(seen)
            for it in await p.evaluate(EXTRACT):
                prev = seen.get(it["urn"])
                if not prev or len(it["text"]) > len(prev["text"]):
                    seen[it["urn"]] = it
            stale = stale + 1 if len(seen) == before else 0
            print(f"collected {len(seen)}", flush=True)
            await p.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await p.wait_for_timeout(3500)   # polite pacing
            more = p.locator('button.scaffold-finite-scroll__load-button')
            if await more.count():
                await more.first.click(); await p.wait_for_timeout(3000)
    posts = []
    for it in seen.values():
        aid = it["urn"].rsplit(":", 1)[1]
        kind = "repost" if it["header"] and "repost" in it["header"].lower() else "post"
        posts.append({**it, "id": aid, "timestamp": ts_from_urn(it["urn"]), "kind": kind,
                      "url": f"https://www.linkedin.com/feed/update/{it['urn']}/"})
    posts.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    (HERE / OUTNAME).write_text(json.dumps(posts, indent=1, ensure_ascii=False))
    print(len(posts), "posts saved;", sum(p["kind"] == "post" for p in posts), "original,", sum(p["kind"] == "repost" for p in posts), "reposts")


asyncio.run(main())
