"""Apply a lab-member contribution submitted through the GitHub issue forms (run by .github/workflows/contributions.yml).

Issue title prefix decides the type:
  [Photo]        -> images + entries in src/data/gallery-uploads.json
  [News]         -> entry (and optional image) in src/data/news.json
  [Publication]  -> new paper in publications-added.json, or venue / project page / code for a listed paper
  [Profile]      -> not applied automatically (maintainer review); exits 3

Images: downloaded, auto-rotated, ALL metadata removed (incl. GPS), resized to <= 2000 px, saved as JPEG.
Writes contribution-result.md (comment text). Exit 0 = applied, 2 = nothing usable, 3 = needs human review.
"""
import datetime as dt
import difflib
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "src/data"
MAX_SIDE = 2000
TODAY = dt.date.today().isoformat()
KIND_TO_CATEGORY = {
    "Conference presentation or poster": "Conferences & events", "Graduation or thesis defense": "Graduations & defenses",
    "Award or recognition": "Awards", "Talk, keynote or panel": "Talks & keynotes", "Lab event or group photo": "Lab life",
    "Field work, robots or experiments": "Field work & robots", "Outreach or teaching": "Outreach", "Something else": "Lab life",
}
CATEGORY = {"Conference or workshop paper": "conferences", "Journal article": "journals", "Preprint": "preprints"}
LABEL = {"journals": "Journal Articles", "conferences": "Conference Proceedings", "preprints": "Preprints"}


def sections(body):
    out, cur = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.*)$", line)
        if m: cur = m.group(1).strip().lower(); out[cur] = []
        elif cur is not None: out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def get(f, *names):
    for n in names:
        for k, v in f.items():
            if k.startswith(n.lower()) and v and v.strip() not in ("_No response_", "None"):
                return v.strip()
    return None


slugify = lambda s, n=40: re.sub(r"[^a-z0-9]+", "-", (s or "item").lower()).strip("-")[:n] or "item"
norm = lambda t: re.sub(r"[^a-z0-9]", "", (t or "").lower())


def image_urls(md):
    urls = re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", md or "") + re.findall(r'<img[^>]+src="(https?://[^"]+)"', md or "")
    urls += [u for u in re.findall(r"(https://github\.com/user-attachments/assets/[0-9a-f-]+)", md or "") if u not in urls]
    return list(dict.fromkeys(urls))


def save_image(url, dest_dir, stem, token):
    headers = {"User-Agent": "scslab-site-bot", **({"Authorization": f"Bearer {token}"} if token and "github.com" in url else {})}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        im = Image.open(io.BytesIO(r.read()))
    im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    dest_dir.mkdir(parents=True, exist_ok=True)
    im.save(dest_dir / f"{stem}.jpg", "JPEG", quality=85, optimize=True, progressive=True)
    return im.size


def load(path, default):
    p = D / path
    return json.loads(p.read_text()) if p.exists() else default


def dump(path, data):
    (D / path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def photo(issue, f, token):
    caption = get(f, "caption") or ""
    kind = get(f, "what is this photo") or "Something else"
    paper, event, people = get(f, "paper presented"), get(f, "event"), get(f, "people in the photo")
    entries = []
    for i, u in enumerate(image_urls(get(f, "photos") or ""), 1):
        stem = f"{TODAY}-{issue['number']}-{slugify(caption)}-{i}"
        try: w, h = save_image(u, ROOT / "public/assets/gallery/uploads", stem, token)
        except Exception as e: print("skip", u, e); continue
        entries.append({"src": f"/assets/gallery/uploads/{stem}.jpg", "size": [w, h], "caption": caption, "date": get(f, "date"),
                        "category": KIND_TO_CATEGORY.get(kind, "Lab life"), "link": get(f, "related link"),
                        "credit": get(f, "photo credit") or f"Photo: {issue['user']['login']}", "alt": caption[:140],
                        "paper": paper, "event": event, "people": people, "issue": issue["number"], "added": TODAY})
    if not entries: return 2, "No photos could be read from this submission."
    dump("gallery-uploads.json", load("gallery-uploads.json", []) + entries)
    return 0, f"Added **{len(entries)}** photo(s) to the [gallery](https://self-aware-complex-systems-lab.github.io/gallery/)."


def news(issue, f, token):
    headline = get(f, "headline")
    if not headline: return 2, "A headline is required."
    date = get(f, "date") or TODAY
    image = None
    urls = image_urls(get(f, "image") or "")
    if urls:
        stem = f"{date}-{slugify(headline)}"
        try: save_image(urls[0], ROOT / "public/assets/news", stem, token); image = f"/assets/news/{stem}.jpg"
        except Exception as e: print("image skipped", e)
    item = {"date": date, "type": get(f, "type"), "title": headline, "body": get(f, "details"), "link": get(f, "link"), "image": image,
            "issue": issue["number"], "addedBy": issue["user"]["login"], "added": TODAY}
    items = sorted([item] + load("news.json", []), key=lambda x: str(x.get("date")), reverse=True)
    dump("news.json", items)
    return 0, "News published on the [home page](https://self-aware-complex-systems-lab.github.io/) and [News](https://self-aware-complex-systems-lab.github.io/news/)."


def publication(issue, f, token):
    title = get(f, "paper title")
    if not title: return 2, "A paper title is required."
    cat = CATEGORY.get(get(f, "type") or "", "conferences")
    venue, year = get(f, "venue"), get(f, "year")
    year = int(year) if year and year.isdigit() else None
    links = {k: v for k, v in (("projectPage", get(f, "project page")), ("code", get(f, "code"))) if v}
    who = f"issue #{issue['number']} by @{issue['user']['login']}, {TODAY}"
    if (get(f, "i want to") or "").startswith("Add"):
        added = load("publications-added.json", [])
        key = f"added:{len(added)}"
        url = get(f, "paper link")
        authors = " and ".join(a.strip() for a in (get(f, "authors") or "").split(",") if a.strip()) or None
        added.append({"category": cat, "categoryLabel": LABEL[cat], "number": None, "title": title, "authors": authors, "venue": venue,
                      "year": year, "date": None, "type": None, "citationsAsOfArchive": None, "url": url,
                      "doi": (re.search(r"doi\.org/(.+)$", url or "") or [None, None])[1], "source": who})
        dump("publications-added.json", added)
        msg = f"Added **{title}**."
    else:
        pubs = [(f"archived:{i}", p) for i, p in enumerate(load("publications.json", []))] + [(f"added:{i}", p) for i, p in enumerate(load("publications-added.json", []))]
        best = max(pubs, key=lambda kp: difflib.SequenceMatcher(None, norm(kp[1]["title"]), norm(title)).ratio())
        if difflib.SequenceMatcher(None, norm(best[1]["title"]), norm(title)).ratio() < 0.9:
            return 3, f"Could not find a listed paper titled “{title}”. A maintainer will take a look."
        key = best[0]
        if venue:
            v = load("publication-venues.json", {"venues": {}})
            v["venues"][key] = {"category": cat, "venue": venue, "year": year, "evidence": who}
            dump("publication-venues.json", v)
        msg = f"Updated **{best[1]['title']}**."
    if links:
        l = load("publication-links.json", {"links": {}})
        l["links"][key] = {**l["links"].get(key, {}), **links}
        dump("publication-links.json", l)
    return 0, msg + " See [Publications](https://self-aware-complex-systems-lab.github.io/publications/)."


def main():
    issue = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["issue"]
    f = sections(issue.get("body", ""))
    token = os.environ.get("GITHUB_TOKEN")
    t = issue["title"]
    if t.startswith("[Photo]"): code, msg = photo(issue, f, token)
    elif t.startswith("[News]"): code, msg = news(issue, f, token)
    elif t.startswith("[Publication]"): code, msg = publication(issue, f, token)
    else: code, msg = 3, "Thanks! A maintainer will review this and update the website."
    Path("contribution-result.md").write_text(msg + "\n")
    print(msg)
    sys.exit(code)


if __name__ == "__main__":
    main()
