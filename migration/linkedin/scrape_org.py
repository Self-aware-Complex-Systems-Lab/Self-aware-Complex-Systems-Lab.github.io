"""Collect a LinkedIn company page's posts (new 2026 "SDUI" layout) with the saved session, then download every
post image at full size.

    .venv/bin/python migration/linkedin/scrape_org.py <slug> [max_posts=200]
Output: migration/linkedin/org-<slug>.json and images in migration/linkedin/images/org-<slug>-<postid>-<n>.<ext>
"""
import asyncio, datetime as dt, hashlib, io, json, re, sys
from pathlib import Path
import requests
from PIL import Image
from linkedin_scraper import BrowserManager

HERE = Path(__file__).parent
SLUG = sys.argv[1]
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 200
FEED = f"https://www.linkedin.com/company/{SLUG}/posts/?feedView=all&sortBy=recent"
SKIP = re.compile(r"profile-displayphoto|company-logo|/emoji|static\.licdn|-logo_", re.I)

EXTRACT = r"""() => [...document.querySelectorAll('[role="listitem"][componentkey^="update-card"]')].map(card => {
  const a = card.querySelector('a[href*="/feed/update/"]');
  const textEl = card.querySelector('[data-testid="expandable-text-box"]');
  const imgs = [...card.querySelectorAll('img')].flatMap(i => [i.currentSrc || i.src, ...((i.getAttribute('srcset') || '').split(',').map(s => s.trim().split(' ')[0]))])
    .filter(u => u && u.startsWith('https://media.licdn.com/'));
  const links = [...(textEl ? textEl.querySelectorAll('a[href]') : [])].map(x => ({text: x.innerText.trim(), href: x.href}));
  const head = card.innerText.split('\n').slice(0, 6).join(' | ');
  return {key: card.getAttribute('componentkey'), url: a ? a.href.split('?')[0] : null, text: textEl ? textEl.innerText.trim() : '',
          links, images: [...new Set(imgs)], head};
})"""
EXPAND = r"""() => { let n = 0; document.querySelectorAll('[role="listitem"] button').forEach(b => {
  const t = (b.innerText || '').trim().toLowerCase(); if (t === '…more' || t === '...more' || t === 'more') { b.click(); n++; } }); return n; }"""


def ts(url):
    m = re.search(r"urn:li:(?:share|activity|ugcPost):(\d+)", url or "")
    return dt.datetime.fromtimestamp((int(m.group(1)) >> 22) / 1000, dt.timezone.utc).isoformat(timespec="seconds") if m else None


def approx_date(head):
    """LinkedIn shows relative ages ('2d', '3w', '9mo', '1yr'); convert to an approximate ISO date (scrape day minus age)."""
    m = re.search(r"\b(\d+)\s*(h|d|w|mo|yr)\b", head or "")
    if not m: return None
    n, u = int(m.group(1)), m.group(2)
    days = {"h": 0, "d": n, "w": 7 * n, "mo": 30 * n, "yr": 365 * n}[u]
    return (dt.date.today() - dt.timedelta(days=days)).isoformat()


def size_of(u):
    m = re.search(r"(?:shrink|scale)_(\d+)(?:_(\d+))?", u)
    return int(m.group(1)) * (int(m.group(2)) if m.group(2) else 1) if m else 0


async def main():
    seen = {}
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        p = b.page
        await p.goto(FEED, wait_until="domcontentloaded")
        await p.wait_for_timeout(7000)
        stale = 0
        while len(seen) < LIMIT and stale < 5:
            await p.evaluate(EXPAND); await p.wait_for_timeout(800)
            before = len(seen)
            for it in await p.evaluate(EXTRACT):
                k = it["url"] or it["key"]
                if k and (k not in seen or len(it["text"]) > len(seen[k]["text"]) or len(it["images"]) > len(seen[k]["images"])):
                    seen[k] = it
            stale = stale + 1 if len(seen) == before else 0
            print(f"{SLUG}: {len(seen)}", flush=True)
            # the new layout lazy-loads inside a list: bring the last card into view, then try "Show more"
            await p.evaluate("""() => { const c = document.querySelectorAll('[role="listitem"][componentkey^="update-card"]');
                                         if (c.length) c[c.length - 1].scrollIntoView({block: 'end'}); window.scrollBy(0, 1200); }""")
            await p.wait_for_timeout(2500)
            more = p.get_by_role("button", name=re.compile(r"show more", re.I))
            if await more.count():
                try: await more.first.click(timeout=2000)
                except Exception: pass
            await p.mouse.wheel(0, 3000)
            await p.wait_for_timeout(3500)
    posts = []
    for it in seen.values():
        best = {}
        for u in it["images"]:
            if SKIP.search(u): continue
            m = re.search(r"/dms/image/(?:sync/)?v2/([A-Za-z0-9_-]+)/", u)
            if m and (m.group(1) not in best or size_of(u) > size_of(best[m.group(1)])): best[m.group(1)] = u
        m = re.search(r"(\d{15,})", it["url"] or "")
        pid = m.group(1) if m else hashlib.sha1(it["key"].encode()).hexdigest()[:12]   # unique per card
        files = []
        for n, (mid, u) in enumerate(best.items(), 1):
            try:
                r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0"}); im = Image.open(io.BytesIO(r.content)); im.load()
            except Exception as e:
                files.append({"sourceUrl": u, "status": f"failed: {type(e).__name__}"}); continue
            if min(im.size) < 120: continue
            ext = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}.get(im.format, "jpg")
            fn = f"org-{SLUG}-{pid}-{n}.{ext}"
            (HERE / "images" / fn).write_bytes(r.content)
            files.append({"file": f"migration/linkedin/images/{fn}", "size": list(im.size), "sha256": hashlib.sha256(r.content).hexdigest(), "status": "ok"})
        posts.append({"org": SLUG, "url": it["url"], "timestamp": ts(it["url"]), "approxDate": approx_date(it["head"]),
                      "text": it["text"], "links": it["links"],
                      "header": it["head"], "images": files})
    posts.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    (HERE / f"org-{SLUG}.json").write_text(json.dumps(posts, indent=1, ensure_ascii=False))
    print(f"{SLUG}: {len(posts)} posts, {sum(f['status']=='ok' for p in posts for f in p['images'])} images")


asyncio.run(main())
