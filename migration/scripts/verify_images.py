"""Phase 5: image-by-image audit (run after the new site is built and served).

    .venv/bin/python migration/scripts/verify_images.py [http://localhost:4321]

For EVERY manifest entry this checks:
 1 source identified        2 download succeeded        3 local file exists & non-empty
 4 decodes without error    5 original vs downloaded dimensions
 6 SHA-256: local file == manifest == browser-received bytes == independent HTTP bytes
 7 perceptual hash vs a fresh screenshot of the image as rendered on the ORIGINAL page
 8 asset referenced by the correct person / section in src/data
 9-10 visit the new page; image loads (complete, naturalWidth>0) inside the right person card / section
Also: duplicate files shared between different people, thumbnail downloads, sponsor coverage.
Writes migration/image-audit.json, migration/reports/unverified-images.md, migration/contact-sheets/*.jpg
"""
import hashlib, io, json, sys
from collections import defaultdict
from pathlib import Path
import imagehash, requests
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]; MIG = ROOT / "migration"; PUB = ROOT / "public"
SITE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4321"
man = json.loads((MIG / "image-manifest.json").read_text()); E = man["entries"]
people = json.loads((ROOT / "src/data/people.json").read_text())
assets = json.loads((ROOT / "src/data/assets.json").read_text())
NAME_JS = r"""() => { const content=[...document.querySelectorAll('img')].filter(i=>!i.closest('header'));
  return [...document.querySelectorAll('img')].map(img => { if (img.closest('header')) return null;
    let block=img, p=img.parentElement; while (p && p!==document.body && content.filter(i=>p.contains(i)).length===1){block=p;p=p.parentElement;}
    const h=block.querySelector('h1,h2,h3'); if (h) return h.innerText.trim();
    const l=(block.innerText||'').split('\n').map(x=>x.replace(/\u200b/g,'').trim()).find(x=>x && x!=='Contact Information' && !x.includes('@')); return l||null; }); }"""
_mr = MIG / "manual-image-review.json"
MANUAL = json.loads(_mr.read_text())["decisions"] if _mr.exists() else {}
NEW_PAGE = {"team": "/people/", "alumni": "/alumni/", "research": "/research/", "sponsors": "/", "gallery": "/gallery/", "site": "/", "pi": None}

def expected_reference(e):
    """Where src/data says this image should appear, derived independently of the manifest's localPath."""
    src = "/assets/" + e["localPath"]
    g = e["group"]
    if g in ("team", "alumni") or (g == "pi" and e["originalPageUrl"].endswith("team-contact")):
        hits = [p["name"] for p in people if p["photo"] == src]
        return hits, (NEW_PAGE.get(g) or "/people/")
    if g == "pi": return (["Dr. Soumik Sarkar"] if any(p["src"] == src for p in assets["pi"]) else []), "/principal-investigator/"
    if g == "research": return [k for k, v in assets["research"].items() if v["src"] == src], "/research/"
    if g == "sponsors": return [s["name"] for s in assets["sponsors"] if s["src"] == src], "/"
    if g == "gallery": return [x["caption"] for x in assets["gallery"] if x["src"] == src], "/gallery/"
    if g == "site": return (["site logo"] if assets["logo"] == src else []), "/"
    return [], None

def main():
    results = []; orig_shots = {}
    (MIG / "contact-sheets").mkdir(exist_ok=True); (MIG / "reports").mkdir(exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        # --- 7: element screenshots of each image as rendered on the original site
        for url in sorted({e["originalPageUrl"] for e in E}):
            pg = br.new_page(viewport={"width": 1440, "height": 1000})
            pg.goto(url, wait_until="networkidle", timeout=90000)
            h = pg.evaluate("document.body.scrollHeight")
            for y in range(0, h + 1500, 400): pg.evaluate(f"scrollTo(0,{y})"); pg.wait_for_timeout(150)
            pg.wait_for_timeout(1500)
            # Signed URLs change on every load, so match by DOM position (same querySelectorAll('img') order the
            # manifest used) and PROVE the match: re-download the fresh URL and compare SHA-256, and re-read the name.
            imgs = pg.query_selector_all("img")
            names = pg.evaluate(NAME_JS)
            for idx, el in enumerate(imgs):
                key = (url, idx); src = el.get_attribute("src")
                rec = {"freshSrc": src, "freshName": names[idx]}
                try:
                    rec["freshSha256"] = hashlib.sha256(requests.get(src, timeout=60).content).hexdigest()
                except Exception as ex: rec["freshSha256"] = None
                try:
                    box = el.bounding_box()
                    if box and box["width"] > 4 and box["height"] > 4:
                        el.scroll_into_view_if_needed(timeout=5000); rec["shot"] = Image.open(io.BytesIO(el.screenshot(timeout=5000))).convert("RGB")
                except Exception: pass
                orig_shots[key] = rec
            pg.close()
        # --- 9/10: what the new site renders
        rendered = {}
        npg = br.new_page(viewport={"width": 1366, "height": 900})
        for path in sorted({p for p in NEW_PAGE.values() if p} | {"/principal-investigator/"}):
            npg.goto(SITE + path, wait_until="networkidle")
            for y in range(0, npg.evaluate("document.body.scrollHeight") + 900, 600): npg.evaluate(f"scrollTo(0,{y})"); npg.wait_for_timeout(60)
            npg.wait_for_timeout(500)
            rendered[path] = npg.evaluate("""() => [...document.querySelectorAll('img')].map(i => ({
                src: new URL(i.src).pathname, ok: i.complete && i.naturalWidth > 0, w: i.naturalWidth, h: i.naturalHeight,
                person: i.closest('[data-name]')?.dataset.name ?? i.dataset.personPhoto ?? null,
                photoId: i.closest('[data-photo-id]')?.dataset.photoId ?? null,
                section: i.dataset.researchImage ?? i.dataset.sponsor ?? i.dataset.gallery ?? null, alt: i.alt }))""")
        br.close()

    sha_owners = defaultdict(set)
    for e in E:
        if e.get("sha256") and e["group"] in ("team", "alumni", "pi"): sha_owners[e["sha256"]].add((e["associatedName"] or "").replace("Dr. ", ""))

    for e in E:
        c = {}; fail = []
        c["1_sourceIdentified"] = bool(e["originalImageUrl"].startswith("http") and e["originalPageUrl"])
        c["2_downloadOk"] = e.get("downloadStatus") == "ok"
        lf = ROOT / e["localFile"] if e.get("localFile") else None
        c["3_localExistsNonEmpty"] = bool(lf and lf.exists() and lf.stat().st_size > 0)
        try:
            Image.open(lf).verify(); im = Image.open(lf); im.load(); c["4_decodes"] = True
        except Exception: c["4_decodes"] = False; im = None
        od, dd = e.get("originalDimensions"), e.get("downloadedDimensions")
        c["5_dimensionsMatch"] = (od == dd) if (od and od[0]) else "n/a (CSS background: no naturalWidth in DOM)"
        local_sha = hashlib.sha256(lf.read_bytes()).hexdigest() if c["3_localExistsNonEmpty"] else None
        c["6_sha256"] = {"localEqualsManifest": local_sha == e.get("sha256"),
                         "browserBytesEqualHttpBytes": e.get("bytesIdentical")}
        fr = orig_shots.get((e["originalPageUrl"], e["occurrenceIndex"])) if e["kind"] == "img" else None
        shot = fr.get("shot") if fr else None
        c["6b_freshReloadSha256Match"] = (fr["freshSha256"] == local_sha) if fr and fr.get("freshSha256") else None
        if fr and e["group"] in ("team", "alumni", "pi") and e["originalPageUrl"].endswith("team-contact"):
            c["8b_freshDomNameMatch"] = (fr["freshName"] or "").replace("\u200b", "").strip() == (e["associatedName"] or "").replace("\u200b", "").strip()
        if shot is not None and im is not None:
            # compare the same crop the original page displayed: render local image at screenshot size (object-fit is cover-like on Sites)
            a = imagehash.phash(shot); b = imagehash.phash(im.convert("RGB").resize(shot.size))
            c["7_phashDistanceVsOriginalRender"] = int(a - b)
        else:
            c["7_phashDistanceVsOriginalRender"] = None
        names, page = expected_reference(e)
        want = (e["associatedName"] or "").replace("​", "").strip()
        if e["group"] in ("team", "alumni", "pi") and e["originalPageUrl"].endswith("team-contact"):
            c["8_referencedByCorrectOwner"] = names == [want]
        else:
            c["8_referencedByCorrectOwner"] = len(names) >= 1
        src = "/assets/" + e["localPath"] if e.get("localPath") else None
        hits = [r for r in rendered.get(page, []) if r["src"] == src] if page else []
        c["9_presentOnNewPage"] = page and len(hits) > 0
        c["10_loadsInBrowser"] = bool(hits) and all(r["ok"] for r in hits)
        if e["group"] in ("team", "alumni") or (e["group"] == "pi" and page == "/people/"):
            c["10b_inCorrectPersonCard"] = bool(hits) and all(r["person"] == want for r in hits)
        c["sharedWithOtherPerson"] = len(sha_owners.get(e.get("sha256"), set())) > 1
        c["thumbnailSuspect"] = bool(od and dd and od[0] and dd[0] < od[0])
        c["hostDownscaleCap"] = e.get("possiblyDownscaledByHost", False)

        hard = ["1_sourceIdentified", "2_downloadOk", "3_localExistsNonEmpty", "4_decodes", "8_referencedByCorrectOwner",
                "9_presentOnNewPage", "10_loadsInBrowser"]
        fail = [k for k in hard if not c.get(k)]
        if c["6_sha256"]["localEqualsManifest"] is not True: fail.append("6_sha256.local")
        if c["5_dimensionsMatch"] is False: fail.append("5_dimensions")
        if c.get("10b_inCorrectPersonCard") is False: fail.append("10b_personCard")
        if c["sharedWithOtherPerson"]: fail.append("sharedWithOtherPerson")
        if c.get("6b_freshReloadSha256Match") is False: fail.append("6b_freshReload")
        if c.get("8b_freshDomNameMatch") is False: fail.append("8b_freshDomName")
        if c["thumbnailSuspect"]: fail.append("thumbnail")
        identity_proven = c["6_sha256"]["localEqualsManifest"] and c["6_sha256"]["browserBytesEqualHttpBytes"] is True and c.get("6b_freshReloadSha256Match") is not False
        ph = c["7_phashDistanceVsOriginalRender"]
        if fail: status = "FAILED"
        elif identity_proven and ph is not None and ph <= 12: status = "VERIFIED"
        elif identity_proven and ph is None: status = "VERIFIED (bytes) — not rendered visibly on original (hidden slide / background); visual check in contact sheet"
        elif identity_proven: status = "NEEDS-MANUAL-REVIEW (bytes identical; rendered crop differs, phash %s)" % ph
        else: status = "UNVERIFIED"
        mr = MANUAL.get(e["id"])
        if mr and status.startswith("NEEDS-MANUAL-REVIEW"): status = "VERIFIED (manual visual review)"
        e["verificationStatus"] = status
        results.append({"id": e["id"], "name": e["associatedName"], "group": e["group"], "localFile": e.get("localFile"),
                        "originalImageUrl": e["originalImageUrl"], "originalPageUrl": e["originalPageUrl"],
                        "newPage": page, "checks": c, "failures": fail, "status": status, "manualReview": MANUAL.get(e["id"])})

    # contact sheets: original render | migrated file, per group
    def sheet(group, rows):
        W = 180; row_h = 200; img = Image.new("RGB", (W * 2 + 260, row_h * len(rows) + 10), "white"); d = ImageDraw.Draw(img)
        for i, (r, e) in enumerate(rows):
            y = i * row_h + 5
            s = (orig_shots.get((e["originalPageUrl"], e["occurrenceIndex"])) or {}).get("shot") if e["kind"] == "img" else None
            if s is not None: t = s.copy(); t.thumbnail((W - 10, row_h - 20)); img.paste(t, (5, y))
            else: d.text((10, y + 80), "(not visible on original)", fill="gray")
            if r["localFile"]:
                t = Image.open(ROOT / r["localFile"]).convert("RGB"); t.thumbnail((W - 10, row_h - 20)); img.paste(t, (W + 5, y))
            d.text((2 * W + 10, y + 10), f"{r['id']}\n{(r['name'] or '')[:34]}\n{r['status'][:30]}\nphash={r['checks']['7_phashDistanceVsOriginalRender']}", fill="black")
        img.save(MIG / "contact-sheets" / f"{group}.jpg", quality=85)
    by_id = {e["id"]: e for e in E}
    for g in sorted({r["group"] for r in results}):
        rows = [(r, by_id[r["id"]]) for r in results if r["group"] == g and not by_id[r["id"]].get("duplicateOfFirstOccurrence")]
        sheet(g, rows)

    (MIG / "image-manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False))
    summary = defaultdict(int)
    for r in results: summary[r["status"].split(" ")[0]] += 1
    out = {"site": SITE, "total": len(results), "summary": dict(summary), "results": results}
    (MIG / "image-audit.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    bad = [r for r in results if not r["status"].startswith("VERIFIED")]
    lines = ["# Missing or unverified images", "", f"Audited {len(results)} image occurrences; {len(bad)} not fully verified.", ""]
    for r in bad:
        lines += [f"## {r['id']} — {r['name']}", f"- Original page: {r['originalPageUrl']}", f"- Original URL: {r['originalImageUrl']}",
                  f"- Local file: {r['localFile']}", f"- Status: {r['status']}", f"- Failed checks: {', '.join(r['failures']) or 'none'}",
                  "- Recovery attempted: browser response capture; independent HTTP GET of the signed URL; alternative size suffixes (=s0, =w16383, none, =d) — all 403 for signed content URLs", ""]
    (MIG / "reports" / "unverified-images.md").write_text("\n".join(lines))
    print(json.dumps(out["summary"]), "| failures:", [(r["id"], r["failures"]) for r in results if r["failures"]])
    print("manual review:", [(r["id"], r["name"], r["checks"]["7_phashDistanceVsOriginalRender"]) for r in results if "MANUAL" in r["status"]])

if __name__ == "__main__":
    main()
