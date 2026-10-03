"""Phase 3: structured content from the rendered original pages.

people.json  - one record per person block on Team & Contact. The photo is linked by the
               image occurrence id from image-manifest.json (same DOM block), never by order.
pi.json, research.json, home.json - verbatim text, split into the original sections.
All text is kept verbatim (only zero-width spaces / nbsp normalised); nothing is rewritten.
"""
import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]; DATA = ROOT / "src/data"; MIG = ROOT / "migration"
BASE = "https://sites.google.com/view/scslab-isu/"
clean = lambda s: re.sub(r"[ \t]+", " ", (s or "").replace("​", "").replace("\xa0", " ")).strip()

# Walk <section>s in order; each person = DOM block holding one content image (same rule as recover_images.py).
TEAM_JS = r"""() => {
  const content = [...document.querySelectorAll('img')].filter(i => !i.closest('header'));
  const h2s = [...document.querySelectorAll('h2')].filter(h => !h.closest('header'));
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  return content.map((img, idx) => {
    let block = img, p = img.parentElement;
    while (p && p !== document.body && content.filter(i => p.contains(i)).length === 1) { block = p; p = p.parentElement; }
    let cat = null; for (const h of h2s) if (before(h, img) && !block.contains(h)) cat = h.innerText.trim();
    const paras = [...block.querySelectorAll('p, h1, h2, h3, li')].filter(e => !e.querySelector('p, h1, h2, h3, li'))
       .map(e => ({tag: e.tagName.toLowerCase(), text: e.innerText}));
    return {src: img.currentSrc || img.src, category: cat, heads: [...block.querySelectorAll('h1,h2,h3')].map(h => h.innerText.trim()).filter(Boolean),
            paras, text: block.innerText, links: [...block.querySelectorAll('a[href]')].map(a => ({href: a.href, text: a.innerText.trim()}))};
  });
}"""

SECTION_JS = r"""() => [...document.querySelectorAll('h1, h2, h3, p, li')].filter(e => !e.closest('header') && !e.querySelector('p, h1, h2, h3, li'))
   .map(e => ({tag: e.tagName.toLowerCase(), text: e.innerText, links: [...e.querySelectorAll('a[href]')].map(a => ({href: a.href, text: a.innerText.trim()}))}))"""

LINK_LABELS = {"linkedin", "google scholar", "personal website", "cv", "website"}
DEG = re.compile(r"^(Ph\.?\s?D|M\.?\s?S|B\.?\s?S|B\.?\s?E|B\.?\s?Tech|M\.?\s?Tech|B\.Tech|M\.Tech|Comajor|Erasmus|Ph\.D\.)", re.I)

def load(page, url):
    page.goto(url, wait_until="networkidle", timeout=90000)
    h = page.evaluate("document.body.scrollHeight")
    for y in range(0, h + 1500, 500): page.evaluate(f"scrollTo(0,{y})"); page.wait_for_timeout(150)
    page.wait_for_timeout(1500)

def person(b, manifest_by_src):
    lines = [clean(p["text"]) for p in b["paras"]]; lines = [l for l in lines if l]
    name = clean(b["heads"][0]) if b["heads"] else next(l for l in lines if l != "Contact Information" and "@" not in l)
    emails = [l for l in lines if re.search(r"\(\s*@\s*\)|\(@\)|@\)?iastate", l) or l == "N/A"]
    rest = [l for l in lines if l not in emails and l != "Contact Information" and l != name and l.lower() not in LINK_LABELS]
    details = [l for l in rest if len(l) < 140 and not l.endswith(".") or DEG.match(l)]
    bio = [l for l in rest if l not in details]
    links = [{"label": clean(l["text"]), "href": l["href"]} for l in b["links"] if clean(l["text"])]
    img = manifest_by_src.get(b["src"])
    return {"name": name, "category": b["category"], "contactEmailAsListed": emails[0] if emails else None,
            "lines": rest, "details": details, "bio": bio, "links": links,
            "photo": ("/assets/" + img["localPath"]) if img else None, "photoManifestId": img["id"] if img else None,
            "rawBlockText": clean(b["text"]).replace(" \n", "\n"), "source": BASE + "team-contact"}

def sections(items):
    out, cur = [], None
    for it in items:
        t = clean(it["text"])
        if not t: continue
        if it["tag"] in ("h1", "h2"):
            cur = {"heading": t, "level": it["tag"], "items": []}; out.append(cur)
        else:
            if cur is None: cur = {"heading": None, "items": []}; out.append(cur)
            cur["items"].append({"tag": it["tag"], "text": t, "links": [l for l in it["links"]]})
    return out

def main():
    man = json.loads((MIG / "image-manifest.json").read_text())
    by_src = {e["originalImageUrl"]: e for e in man["entries"] if e["originalPageUrl"].endswith("team-contact")}
    with sync_playwright() as pw:
        br = pw.chromium.launch(); page = br.new_page(viewport={"width": 1440, "height": 1000})
        load(page, BASE + "team-contact"); blocks = page.evaluate(TEAM_JS)
        # Signed URLs are per-load; fall back to matching by occurrence order *within the same DOM walk*
        # only if the URL differs, and record that the match was confirmed by name.
        people = []
        by_idx = [e for e in man["entries"] if e["originalPageUrl"].endswith("team-contact") and not e["inHeader"] and e["kind"] == "img"]
        for i, b in enumerate(blocks):
            p = person(b, by_src)
            if p["photo"] is None and i < len(by_idx):
                cand = by_idx[i]
                if cand["associatedName"] and cand["associatedName"].replace("​", "").strip() == p["name"]:
                    p["photo"] = "/assets/" + cand["localPath"]; p["photoManifestId"] = cand["id"]; p["photoMatch"] = "same DOM position + name confirmed"
            people.append(p)
        # people without any image (text-only blocks) — detect h3/h1 names not covered
        all_heads = page.evaluate("[...document.querySelectorAll('h1,h3')].filter(h=>!h.closest('header')).map(h=>h.innerText.trim())")
        pages = {}
        for slug in ["home", "principal-investigator", "research", "media"]:
            load(page, BASE + slug); pages[slug] = sections(page.evaluate(SECTION_JS))
        br.close()
    covered = {p["name"] for p in people}
    missing = [h for h in all_heads if clean(h) and clean(h) not in covered and clean(h) not in ("Team & Contact",)]
    (DATA / "people.json").write_text(json.dumps(people, indent=1, ensure_ascii=False))
    for slug, secs in pages.items(): (DATA / f"page-{slug}.json").write_text(json.dumps(secs, indent=1, ensure_ascii=False))
    from collections import Counter
    print(len(people), "people;", Counter(p["category"] for p in people)); print("no photo:", [p["name"] for p in people if not p["photo"]])
    print("headings not matched to a person block:", missing)

if __name__ == "__main__":
    main()
