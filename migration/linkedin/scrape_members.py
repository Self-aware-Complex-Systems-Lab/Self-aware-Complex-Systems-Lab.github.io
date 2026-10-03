"""Visit each lab member's LinkedIn activity feed (URLs in member-urls.json) and keep lab-related posts.

Polite: one profile at a time, 25–45 s random pause between profiles, a few scrolls per feed, max N posts per person.
Keeps a post if it mentions the lab, Prof. Sarkar, TrAC/AIIRA/COALESCE, Iowa State, or looks like a paper/talk/defense
announcement. Downloads that post's images (full size, verified). Resumable: skips people already in members.json.

    .venv/bin/python migration/linkedin/scrape_members.py [max_posts_per_person=40]
"""
import asyncio, datetime as dt, hashlib, io, json, random, re, sys
from pathlib import Path
import requests
from PIL import Image
from linkedin_scraper import BrowserManager

HERE = Path(__file__).parent
OUT = HERE / "members.json"
IMG = HERE / "images"
PER = int(sys.argv[1]) if len(sys.argv) > 1 else 40
RELEVANT = re.compile(r"scslab|self[- ]aware|soumik|sarkar|\btrac\b|translational ai|aiira|coalesce|iowa state|\bisu\b|"
                      r"accepted|publish|paper|journal|conference|workshop|proceedings|arxiv|cvpr|neurips|icml|iclr|aaai|icra|iros|"
                      r"wacv|kdd|corl|defen[cs]e|ph\.?d|graduat|award|keynote|talk|poster|preprint", re.I)
SKIP_IMG = re.compile(r"profile-displayphoto|company-logo|/emoji|static\.licdn|-logo_|profile-framedphoto", re.I)

EXTRACT = r"""() => {
  const out = [];
  const cards = document.querySelectorAll('div[data-urn^="urn:li:activity:"], [role="listitem"][componentkey^="update-card"]');
  cards.forEach(el => {
    const urn = el.getAttribute('data-urn') || '';
    const a = el.querySelector('a[href*="/feed/update/"]');
    const textEl = el.querySelector('.update-components-text, .feed-shared-update-v2__description, [data-testid="expandable-text-box"]');
    const header = (el.querySelector('.update-components-header') || {}).innerText || '';
    const imgs = [...el.querySelectorAll('img')].flatMap(i => [i.currentSrc || i.src, ...((i.getAttribute('srcset') || '').split(',').map(s => s.trim().split(' ')[0]))])
      .filter(u => u && u.startsWith('https://media.licdn.com/'));
    out.push({urn, href: a ? a.href.split('?')[0] : null, header: header.trim(), text: textEl ? textEl.innerText.trim() : '',
              links: [...(textEl ? textEl.querySelectorAll('a[href]') : [])].map(x => ({text: x.innerText.trim(), href: x.href})),
              images: [...new Set(imgs)]});
  });
  return out;
}"""
EXPAND = r"""() => document.querySelectorAll('button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label*="see more" i]').forEach(b => b.click())"""


def ts(s):
    m = re.search(r"urn:li:(?:activity|share|ugcPost):(\d+)", s or "")
    return dt.datetime.fromtimestamp((int(m.group(1)) >> 22) / 1000, dt.timezone.utc).isoformat(timespec="seconds") if m else None


def size_of(u):
    m = re.search(r"(?:shrink|scale)_(\d+)(?:_(\d+))?", u)
    return int(m.group(1)) * (int(m.group(2)) if m.group(2) else 1) if m else 0


def save_images(urls, stem):
    best = {}
    for u in urls:
        if SKIP_IMG.search(u): continue
        m = re.search(r"/dms/image/(?:sync/)?v2/([A-Za-z0-9_-]+)/", u)
        if m and (m.group(1) not in best or size_of(u) > size_of(best[m.group(1)])): best[m.group(1)] = u
    files = []
    for n, u in enumerate(best.values(), 1):
        try:
            r = requests.get(u, timeout=60, headers={"User-Agent": "Mozilla/5.0"}); im = Image.open(io.BytesIO(r.content)); im.load()
        except Exception:
            continue
        if min(im.size) < 160: continue
        fn = f"member-{stem}-{n}.jpg" if im.format == "JPEG" else f"member-{stem}-{n}.{(im.format or 'jpg').lower()}"
        (IMG / fn).write_bytes(r.content)
        files.append({"file": f"migration/linkedin/images/{fn}", "size": list(im.size), "sha256": hashlib.sha256(r.content).hexdigest()})
    return files


async def main():
    urls = json.loads((HERE / "member-urls.json").read_text())
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    IMG.mkdir(exist_ok=True)
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        p = b.page
        for name, url in urls.items():
            if name in done: continue
            feed = url.rstrip("/") + "/recent-activity/all/"
            rec = {"profile": url, "status": "ok", "posts": []}
            try:
                await p.goto(feed, wait_until="domcontentloaded"); await p.wait_for_timeout(5000)
                if any(x in p.url for x in ("/login", "authwall", "checkpoint")):
                    print("STOP: LinkedIn asked to log in / verify — stopping to protect the account."); break
                seen = {}
                for _ in range(6):
                    await p.evaluate(EXPAND); await p.wait_for_timeout(600)
                    for it in await p.evaluate(EXTRACT):
                        k = it["urn"] or it["href"] or it["text"][:80]
                        if k and (k not in seen or len(it["text"]) > len(seen[k]["text"])): seen[k] = it
                    if len(seen) >= PER: break
                    await p.mouse.wheel(0, 3000); await p.wait_for_timeout(2500)
                for it in list(seen.values())[:PER]:
                    if not RELEVANT.search(it["text"] + " " + it["header"]): continue
                    key = it["urn"] or it["href"] or ""
                    pid = (re.search(r"(\d{15,})", key) or [None, hashlib.sha1(it["text"].encode()).hexdigest()[:12]])[1]
                    rec["posts"].append({"url": it["href"] or (f"https://www.linkedin.com/feed/update/{it['urn']}/" if it["urn"] else None),
                                         "timestamp": ts(key), "repost": "repost" in it["header"].lower(), "text": it["text"],
                                         "links": it["links"], "images": save_images(it["images"], pid)})
            except Exception as e:
                rec["status"] = f"error: {type(e).__name__}"
            done[name] = rec
            OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False))
            print(f"{name}: {len(rec['posts'])} relevant posts ({rec['status']})", flush=True)
            await p.wait_for_timeout(random.randint(25000, 45000))
    print("MEMBERS_DONE", len(done))


asyncio.run(main())
