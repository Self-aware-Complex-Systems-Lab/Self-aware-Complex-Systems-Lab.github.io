"""Apply a lab-member contribution submitted through the GitHub issue forms (run by .github/workflows/contributions.yml).

Issue title prefix decides the type:
  [Photo]        -> images + entries in src/data/gallery-uploads.json
  [News]         -> entry (and optional image) in src/data/news.json
  [Publication]  -> new paper in publications-added.json, or venue / project page / code for a listed paper
  [Member]       -> new lab member (photo, degrees, bio, links); if already listed, treated as a profile update
  [Profile]      -> updates an existing person's role, bio, interests, links, photo (only fields that are filled in)
  [Milestone]    -> defense / graduation / leaving: moves the person to the right alumni section, adds the degree, news item
  [Grant]        -> new grant on the PI page + CV (duplicate titles detected), optional announcement link, news item
  [Award]        -> award news item; awards to Prof. Sarkar also go to Honors & Awards (duplicates detected)

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
    if not add_news(item): return 0, "This news item is already on the website."
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


# ---------------------------------------------------------------- people helpers
ROLE_TO_CATEGORY = {
    "Ph.D. student": "Doctoral Students", "Master's student": "Masters Students", "Postdoctoral researcher": "Post Doctoral Students",
    "Undergraduate researcher": "Undergraduate Researchers", "Independent study / visiting student": "Research Students on Independent Studies",
    "Visiting scholar": "Visiting Scholars",
}
ALUMNI_OF = {
    "Doctoral Students": "Graduate Alumni", "Masters Students": "Masters Alumni", "Post Doctoral Students": "Post-doctorate Alumni",
    "Undergraduate Researchers": "Undergraduate Alumni", "Research Students on Independent Studies": "Independent Study Alumni",
    "Visiting Scholars": "Visiting Scholar Alumni",
}
LINK_FIELDS = [("homepage", "homepage"), ("google scholar", "scholar"), ("github", "github"), ("linkedin", "linkedin"), ("orcid", "orcid")]
key_name = lambda n: re.sub(r"[^a-z]", "", re.sub(r"^dr\.?\s*", "", (n or "").lower()))


def everyone():
    base = load("people.json", []) + load("people-added.json", [])
    ov = load("people-overrides.json", {"category": {}})
    return [dict(p, category=ov["category"].get(p["name"], p.get("category"))) for p in base]


def find_person(name):
    """Exact (case/punctuation-insensitive) or near-identical match against everyone listed."""
    k = key_name(name)
    best, score = None, 0.0
    for p in everyone():
        r = 1.0 if key_name(p["name"]) == k else difflib.SequenceMatcher(None, key_name(p["name"]), k).ratio()
        if r > score: best, score = p, r
    return best if score >= 0.9 else None


def add_links(person, f):
    w = load("people-web-links.json", {"links": {}, "interests": {}})
    have = {norm(x["url"]) for x in w["links"].get(person, [])} | {norm(l["href"]) for p in everyone() if p["name"] == person for l in p.get("links", [])}
    new = []
    for label, typ in LINK_FIELDS:
        u = get(f, label)
        if u and u.startswith("http") and norm(u) not in have:
            new.append({"type": typ, "url": u}); have.add(norm(u))
    for line in (get(f, "other links") or "").splitlines():
        u = line.strip()
        if u.startswith("http") and norm(u) not in have:
            new.append({"type": "other", "url": u, "label": "Website"}); have.add(norm(u))
    if new:
        w["links"].setdefault(person, []).extend(new)
        dump("people-web-links.json", w)
    return len(new)


def add_news(item):
    items = load("news.json", [])
    if any(norm(n["title"]) == norm(item["title"]) or difflib.SequenceMatcher(None, norm(n["title"]), norm(item["title"])).ratio() >= 0.8 for n in items):
        return False
    dump("news.json", sorted([item] + items, key=lambda x: str(x.get("date")), reverse=True))
    return True


def save_photo(f, field, name, token, folder="team"):
    urls = image_urls(get(f, field) or "")
    if not urls: return None
    stem = f"{slugify(name)}-{TODAY}"
    save_image(urls[0], ROOT / "public/assets" / folder, stem, token)
    return f"/assets/{folder}/{stem}.jpg"


def month_year(v):
    try: return dt.date.fromisoformat(v).strftime("%B %Y")
    except Exception: return v


# ---------------------------------------------------------------- handlers
def profile_update(issue, f, token, person=None):
    who = person or find_person(get(f, "your name", "name") or "")
    if not who: return 3, f"Could not find “{get(f, 'your name', 'name')}” on the website. Use the New member form, or a maintainer will check."
    name = who["name"]
    profiles = load("people-profiles.json", {})
    pr = profiles.get(name) or {"name": name, "headline": None, "education": [], "affiliation": [], "bio": [], "researchInterests": None,
                                "joined": None, "currentPosition": None, "project": None, "_sources": []}
    changed = []
    for field, key in (("role / headline", "headline"), ("research interests", "researchInterests"), ("current position", "currentPosition"), ("joined", "joined")):
        v = get(f, field)
        if v and v != pr.get(key): pr[key] = v; changed.append(key)
    bio = get(f, "bio")
    if bio: pr["bio"] = [p.strip() for p in bio.split("\n\n") if p.strip()]; changed.append("bio")
    degrees = [d.strip("-• ").strip() for d in (get(f, "degrees") or "").splitlines() if d.strip()]
    for d in degrees:
        if norm(d) not in {norm(e) for e in pr["education"]}: pr["education"].insert(0, d); changed.append("education")
    dept = get(f, "department")
    if dept and dept not in pr.get("affiliation", []): pr["affiliation"] = [dept] + [a for a in pr.get("affiliation", []) if "Department" not in a]; changed.append("department")
    pr.setdefault("_sources", []).append({"fact": f"updated: {', '.join(sorted(set(changed))) or 'links/photo'}", "url": f"issue #{issue['number']}"})
    profiles[name] = pr
    dump("people-profiles.json", profiles)
    nlinks = add_links(name, f)
    pic = save_photo(f, "photo", name, token)
    if pic:
        ov = load("people-overrides.json", {"category": {}, "photo": {}}); ov.setdefault("photo", {})[name] = pic; dump("people-overrides.json", ov)
    bits = ([f"{len(set(changed))} field(s)"] if changed else []) + ([f"{nlinks} new link(s)"] if nlinks else []) + (["new photo"] if pic else [])
    return 0, f"Updated **{name}**: {', '.join(bits) or 'nothing new (everything was already there)'}."


def member(issue, f, token):
    name = get(f, "full name")
    if not name: return 2, "A name is required."
    existing = find_person(name)
    if existing:
        code, msg = profile_update(issue, f, token, existing)
        return code, f"**{existing['name']}** is already on the website, so this was applied as a profile update. " + msg
    role = get(f, "role") or "Ph.D. student"
    added = load("people-added.json", [])
    added.append({"name": name, "category": ROLE_TO_CATEGORY.get(role, "Doctoral Students"), "contactEmailAsListed": get(f, "email"),
                  "photo": None, "source": f"contribute form, issue #{issue['number']}"})
    dump("people-added.json", added)
    profiles = load("people-profiles.json", {})
    dept = get(f, "department")
    profiles[name] = {"name": name, "headline": f"{role}{', ' + dept.replace('Department of ', '') if dept else ''}",
                      "education": [d.strip("-• ").strip() for d in (get(f, "degrees") or "").splitlines() if d.strip()],
                      "affiliation": [f"{dept}, Iowa State University"] if dept and "Iowa State" not in dept else ([dept] if dept else []),
                      "bio": [p.strip() for p in (get(f, "bio") or "").split("\n\n") if p.strip()], "researchInterests": get(f, "research interests"),
                      "joined": get(f, "joined"), "currentPosition": None, "project": None,
                      "_sources": [{"fact": "added via contribute form", "url": f"issue #{issue['number']}"}]}
    dump("people-profiles.json", profiles)
    add_links(name, f)
    pic = save_photo(f, "photo", name, token)
    if pic:
        ov = load("people-overrides.json", {"category": {}, "photo": {}}); ov.setdefault("photo", {})[name] = pic; dump("people-overrides.json", ov)
    add_news({"date": TODAY, "type": "New member", "title": f"Welcome, {name}", "body": f"{name} joins the lab as a {role.lower()}"
              f"{' in the ' + dept if dept else ''}{', ' + get(f, 'joined') if get(f, 'joined') else ''}.", "link": None, "image": pic,
              "issue": issue["number"], "added": TODAY})
    missing = [l for l, _ in LINK_FIELDS if not get(f, l)] + ([] if pic else ["photo"])
    note = f" Still missing: {', '.join(missing)} — add them any time with the Profile update form." if missing else ""
    return 0, f"Added **{name}** to the [People](https://self-aware-complex-systems-lab.github.io/people/) page.{note}"


def milestone(issue, f, token):
    who = find_person(get(f, "who") or "")
    if not who: return 3, f"Could not find “{get(f, 'who')}” on the website. A maintainer will check."
    name, cur = who["name"], who.get("category")
    kind = get(f, "milestone") or ""
    date = get(f, "date") or TODAY
    ov = load("people-overrides.json", {"category": {}, "photo": {}})
    alumni = ALUMNI_OF.get(cur, cur)
    if "M.S." in kind and cur == "Doctoral Students":
        alumni = cur   # M.S. earned along the way: stays a Ph.D. student
    if alumni != cur: ov["category"][name] = alumni
    dump("people-overrides.json", ov)
    profiles = load("people-profiles.json", {})
    pr = profiles.setdefault(name, {"name": name, "headline": None, "education": [], "affiliation": [], "bio": [], "researchInterests": None,
                                    "joined": None, "currentPosition": None, "project": None, "_sources": []})
    degree = get(f, "degree earned")
    if degree and norm(degree) not in {norm(e) for e in pr["education"]}: pr["education"].insert(0, degree)
    nxt = get(f, "next position")
    if nxt: nxt = re.sub(r"^(a|an|the)\s+", "", nxt, flags=re.I); pr["currentPosition"] = nxt
    first = name.replace("Dr. ", "").split()[0]
    sentence = {"Ph.D. thesis defense": f"{first} successfully defended the Ph.D. thesis in {month_year(date)}.",
                "Ph.D. graduation": f"{first} completed the Ph.D. in {month_year(date)}.",
                "M.S. graduation": f"{first} completed the M.S. in {month_year(date)}.",
                "B.S. graduation": f"{first} completed the B.S. in {month_year(date)}.",
                "Postdoc completed": f"{first} completed a postdoctoral appointment in the lab in {month_year(date)}.",
                "Left the lab": f"{first} was a member of the lab until {month_year(date)}."}.get(kind, f"{first}: {kind} ({month_year(date)}).")
    thesis = get(f, "thesis title")
    if thesis: sentence = sentence[:-1] + f", with the thesis “{thesis}”."
    if nxt: sentence += f" {first} is now {'an' if nxt[0].lower() in 'aeiou' else 'a'} {nxt}." if not re.match(r"(at|with|in)\b", nxt, re.I) else f" {first} is now {nxt}."
    if sentence not in pr["bio"]: pr["bio"].append(sentence)
    if alumni != cur and pr.get("headline"):
        yr = month_year(date).split()[-1]
        pr["headline"] = f"{(degree or kind).split(',')[0]} {yr}" if degree or "graduation" in kind or "defense" in kind else pr["headline"]
    pr["_sources"].append({"fact": f"{kind} ({date})", "url": f"issue #{issue['number']}"})
    dump("people-profiles.json", profiles)
    if "Left" not in kind:
        add_news({"date": date, "type": "Thesis defense / graduation", "title": f"{name.replace('Dr. ', '')}: {kind}",
                  "body": sentence, "link": get(f, "link"), "image": save_photo(f, "photo", name, token, "news"), "issue": issue["number"], "added": TODAY})
    moved = f" Moved to **{alumni}**." if alumni != cur else ""
    return 0, f"Recorded **{kind}** for **{name}**.{moved}"


def grant(issue, f, token):
    title = get(f, "grant title")
    if not title: return 2, "A grant title is required."
    role, sponsor, amount = get(f, "dr. sarkar's role") or "PI", get(f, "sponsor"), get(f, "amount")
    start, end, link = get(f, "start"), get(f, "end"), get(f, "announcement link")
    rec = load("funding-recent.json", {"grants": []})
    old = [i["text"] for s in load("page-principal-investigator.json", []) if s["heading"] == "Research Funding" for i in s["items"]]
    tkey = lambda t: norm(re.split(r"\s\(as\b", t)[0])
    dup = next((t for t in [g["text"] for g in rec["grants"]] + old if difflib.SequenceMatcher(None, tkey(t), norm(title)).ratio() >= 0.85), None)
    if dup:
        msg = f"This grant is already listed (“{dup[:90]}…”)."
        text = dup
    else:
        span = " – ".join(x for x in (start, end) if x)
        money = ", ".join(x for x in (amount, span) if x)
        text = f"{title} (as {role})" + (f" sponsored by {sponsor}" if sponsor else "") + (f" ({money})" if money else "")
        rec["grants"].insert(0, {"text": text, "start": start or str(dt.date.today().year), "source": f"issue #{issue['number']}", "kind": role})
        dump("funding-recent.json", rec)
        msg = "Added to Research Funding on the PI page and the CV."
        add_news({"date": TODAY, "type": "New grant", "title": f"New grant: {title}", "body": get(f, "summary") or (f"Funded by {sponsor}." if sponsor else None),
                  "link": link, "image": None, "issue": issue["number"], "added": TODAY})
    if link:
        a = load("grant-announcements.json", {"grants": []})
        if not any(g["grantPrefix"] == text[:60] for g in a["grants"]):
            a["grants"].append({"grantPrefix": text[:60], "url": link, "date": TODAY}); dump("grant-announcements.json", a)
            msg += " Announcement link added."
    return 0, msg


def award(issue, f, token):
    name, recipient = get(f, "award"), get(f, "recipient") or ""
    if not name: return 2, "An award name is required."
    year, link, org = get(f, "year") or str(dt.date.today().year), get(f, "link"), get(f, "awarding organization")
    full = f"{name}{', ' + org if org and org.lower() not in name.lower() else ''}, {year}"
    msgs = []
    if key_name(recipient) in (key_name("Soumik Sarkar"), key_name("Prof. Soumik Sarkar")):
        a = load("awards.json", {"awards": []})
        if any(difflib.SequenceMatcher(None, norm(x["text"]), norm(full)).ratio() >= 0.85 or norm(name) in norm(x["text"]) for x in a["awards"]):
            return 0, "This award is already listed in Honors & Awards — nothing changed."
        else:
            a["awards"].append({"text": full, "url": link})
            a["awards"].sort(key=lambda x: (re.findall(r"(\d{4})\D*$", x["text"]) or ["0"])[-1], reverse=True)
            dump("awards.json", a); msgs.append("Added to Honors & Awards on the PI page and the CV.")
    if add_news({"date": TODAY if not get(f, "date") else get(f, "date"), "type": "Award", "title": f"{recipient}: {name}" if recipient else name,
                 "body": get(f, "details"), "link": link, "image": save_photo(f, "photo", name, token, "news"), "issue": issue["number"], "added": TODAY}):
        msgs.append("News item published.")
    return 0, " ".join(msgs) or "Nothing new — this award is already on the website."


def main():
    issue = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["issue"]
    f = sections(issue.get("body", ""))
    token = os.environ.get("GITHUB_TOKEN")
    t = issue["title"]
    if t.startswith("[Photo]"): code, msg = photo(issue, f, token)
    elif t.startswith("[News]"): code, msg = news(issue, f, token)
    elif t.startswith("[Publication]"): code, msg = publication(issue, f, token)
    elif t.startswith("[Member]"): code, msg = member(issue, f, token)
    elif t.startswith("[Profile]"): code, msg = profile_update(issue, f, token)
    elif t.startswith("[Milestone]"): code, msg = milestone(issue, f, token)
    elif t.startswith("[Grant]"): code, msg = grant(issue, f, token)
    elif t.startswith("[Award]"): code, msg = award(issue, f, token)
    else: code, msg = 3, "Thanks! A maintainer will review this and update the website."
    Path("contribution-result.md").write_text(msg + "\n")
    print(msg)
    sys.exit(code)


if __name__ == "__main__":
    main()
