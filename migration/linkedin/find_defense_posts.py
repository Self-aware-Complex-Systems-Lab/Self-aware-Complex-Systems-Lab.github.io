"""Find thesis-defense / graduation / hooding posts (and their photos) for specific lab members.

For each name: use the known profile URL (member-urls.json) or LinkedIn people search (first result mentioning Iowa State),
read the activity feed deeply (up to N posts), keep posts about a defense/graduation/hooding, download their images.
Output: migration/linkedin/defense-posts.json, images in migration/linkedin/images/defense-<id>-<n>.jpg

    .venv/bin/python migration/linkedin/find_defense_posts.py "Muhammad Arbab Arshad" "Souradeep Chattopadhyay"
"""
import asyncio, json, re, sys, urllib.parse
from pathlib import Path
from linkedin_scraper import BrowserManager
sys.path.insert(0, str(Path(__file__).parent))
from scrape_members import EXTRACT, EXPAND, ts, save_images  # same extraction + image download

HERE = Path(__file__).parent
MAX_POSTS = 150
DEFENSE = re.compile(r"defen[cs]e|defended|dissertation|thesis|ph\.?\s?d|doctor|hood|graduat|commencement|convocation", re.I)


async def profile_url(page, name, known):
    if name in known: return known[name]
    await page.goto("https://www.linkedin.com/search/results/people/?keywords=" + urllib.parse.quote(name), wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    hits = await page.evaluate("""() => [...document.querySelectorAll('a[href*="/in/"]')].map(a => ({href: a.href.split('?')[0],
        text: (a.closest('li, [role="listitem"], div') || a).innerText.slice(0, 300)}))""")
    for h in hits:
        if re.search(r"iowa state|ames|scslab|translational ai|sarkar", h["text"], re.I) and all(p.lower() in h["text"].lower() for p in name.split()[:1]):
            return h["href"].rstrip("/") + "/"
    return None


async def main(names):
    known = json.loads((HERE / "member-urls.json").read_text())
    out_path = HERE / "defense-posts.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    async with BrowserManager(headless=False) as b:
        await b.load_session(str(HERE / "session.json"))
        p = b.page
        for name in names:
            url = await profile_url(p, name, known)
            if not url:
                out[name] = {"profile": None, "posts": [], "note": "profile not found via LinkedIn search"}; print(name, "-> profile not found"); continue
            await p.goto(url.rstrip("/") + "/recent-activity/all/", wait_until="domcontentloaded"); await p.wait_for_timeout(5000)
            if any(x in p.url for x in ("/login", "authwall", "checkpoint")): print("STOP: LinkedIn verification"); break
            seen, stale = {}, 0
            while len(seen) < MAX_POSTS and stale < 4:
                await p.evaluate(EXPAND); await p.wait_for_timeout(600)
                before = len(seen)
                for it in await p.evaluate(EXTRACT):
                    k = it["urn"] or it["href"] or it["text"][:80]
                    if k and (k not in seen or len(it["text"]) > len(seen[k]["text"])): seen[k] = it
                stale = stale + 1 if len(seen) == before else 0
                await p.mouse.wheel(0, 3500); await p.wait_for_timeout(3000)
            hits = []
            for it in seen.values():
                if not DEFENSE.search(it["text"] + " " + it["header"]): continue
                key = it["urn"] or it["href"] or ""
                pid = (re.search(r"(\d{15,})", key) or [None, "x"])[1]
                hits.append({"url": it["href"] or (f"https://www.linkedin.com/feed/update/{it['urn']}/" if it["urn"] else None),
                             "timestamp": ts(key), "repost": "repost" in it["header"].lower(), "text": it["text"],
                             "images": save_images(it["images"], f"defense-{pid}")})
            out[name] = {"profile": url, "postsRead": len(seen), "posts": hits}
            out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
            print(f"{name}: read {len(seen)} posts, {len(hits)} defense/graduation posts, {sum(len(h['images']) for h in hits)} images ({url})", flush=True)
            await p.wait_for_timeout(30000)


asyncio.run(main(sys.argv[1:]))
