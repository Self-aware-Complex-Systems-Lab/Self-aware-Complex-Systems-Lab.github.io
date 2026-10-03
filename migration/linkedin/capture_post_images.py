"""Download every image Prof. Sarkar posted himself (not reposts), at the largest size LinkedIn serves.

Opens each of his own posts that has media, collects all feed-share / article images (including every slide of
multi-image posts), keeps the largest rendition per media id, downloads them, and verifies each with Pillow.
Writes migration/linkedin/images/<post-id>-<n>.<ext> and migration/linkedin/post-images.json.
"""
import asyncio, hashlib, io, json, re
from pathlib import Path
import requests
from PIL import Image
from linkedin_scraper import BrowserManager

HERE = Path(__file__).parent
OUT = HERE / "images"
SKIP = re.compile(r"profile-displayphoto|company-logo|/emoji|static\.licdn|ghost|-logo_", re.I)
MEDIA = re.compile(r"/dms/image/(?:sync/)?v2/([A-Za-z0-9_-]+)/(feedshare|articleshare|image)[^/]*?(?:shrink|scale|_)?_?(\d+)?", re.I)

COLLECT = r"""() => {
  const urls = new Set();
  const root = document.querySelector('div[data-urn^="urn:li:activity:"]') || document.querySelector('main') || document.body;
  root.querySelectorAll('img').forEach(i => {
    [i.currentSrc, i.src, i.getAttribute('data-delayed-url')].forEach(u => u && urls.add(u));
    (i.getAttribute('srcset') || '').split(',').forEach(s => { const u = s.trim().split(' ')[0]; if (u) urls.add(u); });
  });
  return [...urls].filter(u => u.startsWith('https://media.licdn.com/'));
}"""


def size_of(url):
    m = re.search(r"(?:shrink|scale)_(\d+)(?:_(\d+))?", url)
    return int(m.group(1)) * (int(m.group(2)) if m and m.group(2) else 1) if m else 0


async def main():
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "posts.json"          # posts file to process
    out_json = sys.argv[2] if len(sys.argv) > 2 else "post-images.json"
    posts = json.loads((HERE / src).read_text())
    own = [p for p in posts if p["kind"] == "post" and (p["images"] or p.get("article"))]
    OUT.mkdir(exist_ok=True)
    result = []
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        pg = b.page
        for k, post in enumerate(own, 1):
            await pg.goto(post["url"], wait_until="domcontentloaded")
            await pg.wait_for_timeout(4500)
            # step through multi-image carousels so every slide is rendered
            for _ in range(20):
                nxt = pg.locator('button[aria-label*="Next" i]:visible').first
                if not await nxt.count(): break
                try: await nxt.click(timeout=1500); await pg.wait_for_timeout(700)
                except Exception: break
            urls = [u for u in await pg.evaluate(COLLECT) if not SKIP.search(u)]
            best = {}
            for u in urls:
                m = re.search(r"/dms/image/(?:sync/)?v2/([A-Za-z0-9_-]+)/", u)
                if not m: continue
                mid = m.group(1)
                if mid not in best or size_of(u) > size_of(best[mid]): best[mid] = u
            saved = []
            for n, (mid, u) in enumerate(best.items(), 1):
                try:
                    r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
                    im = Image.open(io.BytesIO(r.content)); im.load()
                except Exception as e:
                    saved.append({"mediaId": mid, "sourceUrl": u, "status": f"failed: {type(e).__name__}"}); continue
                if min(im.size) < 120:  # icons / tiny thumbnails
                    continue
                ext = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}.get(im.format, "jpg")
                fn = f"{post['id']}-{n}.{ext}"
                (OUT / fn).write_bytes(r.content)
                saved.append({"file": f"migration/linkedin/images/{fn}", "mediaId": mid, "size": list(im.size),
                              "sha256": hashlib.sha256(r.content).hexdigest(), "sourceUrl": u, "status": "ok"})
            result.append({"postId": post["id"], "timestamp": post["timestamp"], "postUrl": post["url"],
                           "textStart": post["text"][:120], "images": saved})
            print(f"[{k}/{len(own)}] {post['timestamp'][:10]} {sum(s['status']=='ok' for s in saved)} images", flush=True)
            await pg.wait_for_timeout(2500)   # polite pacing
    (HERE / out_json).write_text(json.dumps(result, indent=1, ensure_ascii=False))
    ok = sum(s["status"] == "ok" for r in result for s in r["images"])
    print(f"{ok} images saved from {len(result)} posts; failures:", sum(s['status'] != 'ok' for r in result for s in r['images']))


asyncio.run(main())
