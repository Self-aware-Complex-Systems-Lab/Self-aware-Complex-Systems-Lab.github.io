"""Phase 2: recover every original image occurrence with its DOM association.

For each page the browser's own received bytes are captured (response interception)
and an independent HTTP re-download is made; both SHA-256s are recorded so identity
can be proven. Association is taken from the DOM: the "block" of an image is the
largest ancestor containing exactly one content image, and its category is the
nearest preceding <h2>. Nothing is inferred from file order.

Writes: public/assets/<group>/<file>, migration/image-manifest.json,
        migration/archive/images-raw/<sha>.<ext> (browser bytes, untouched)
"""
import hashlib, io, json, re, sys, time
from pathlib import Path
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migration"; RAW = MIG / "archive" / "images-raw"; PUB = ROOT / "public" / "assets"
BASE = "https://sites.google.com/view/scslab-isu/"
PAGES = ["home", "principal-investigator", "team-contact", "research", "publications", "media"]
CURRENT = {"Principal Investigator", "Post Doctoral Students", "Doctoral Students", "Masters Students",
           "Research Students on Independent Studies"}
ALUMNI = {"Post-doctorate Alumni", "Graduate Alumni", "Undergraduate Alumni"}

JS = r"""() => {
  const all = [...document.querySelectorAll('img')];
  const content = all.filter(i => !i.closest('header'));
  const h2s = [...document.querySelectorAll('h2')].filter(h => !h.closest('header'));
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
  const out = [];
  const describe = (el, kind, src, extra) => {
    // block = largest ancestor that contains exactly one content image
    let block = el;
    if (kind === 'img' && !el.closest('header')) {
      let p = el.parentElement;
      while (p && p !== document.body && content.filter(i => p.contains(i)).length === 1) { block = p; p = p.parentElement; }
    }
    let cat = null, catLevel = null;
    for (const h of h2s) if (before(h, el) && !block.contains(h)) { cat = h.innerText.trim(); catLevel = h.tagName; }
    const heads = [...block.querySelectorAll('h1,h2,h3')].map(h => h.innerText.trim()).filter(Boolean);
    const r = el.getBoundingClientRect();
    out.push(Object.assign({kind, src, inHeader: !!el.closest('header'),
      alt: el.getAttribute('alt') || el.getAttribute('aria-label') || '',
      renderedWidth: Math.round(r.width), renderedHeight: Math.round(r.height),
      docY: Math.round(r.top + scrollY), docX: Math.round(r.left),
      precedingHeading: cat, precedingHeadingTag: catLevel, blockHeadings: heads,
      blockText: (block.innerText || '').trim(),
      blockLinks: [...block.querySelectorAll('a[href]')].map(a => ({href: a.href, text: a.innerText.trim()})),
      linkHref: el.closest('a') ? el.closest('a').href : null}, extra));
  };
  all.forEach(i => describe(i, 'img', i.currentSrc || i.src, {naturalWidth: i.naturalWidth, naturalHeight: i.naturalHeight,
      srcset: i.getAttribute('srcset'), complete: i.complete}));
  document.querySelectorAll('*').forEach(n => {
    const bg = getComputedStyle(n).backgroundImage;
    if (bg && bg.includes('url(')) (bg.match(/url\("?([^")]+)"?\)/g) || []).forEach(u =>
      describe(n, 'css-background', u.replace(/^url\("?|"?\)$/g, ''), {element: n.tagName.toLowerCase()}));
  });
  return out;
}"""

def slugify(s):
    s = re.sub(r"^(dr\.?\s+)", "", (s or "").strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("​", "")).strip("-") or "unnamed"

def name_of(rec):
    """Person/section label from the image's own DOM block (headings first, then first text line)."""
    if rec["blockHeadings"]: return rec["blockHeadings"][0].replace("​", "").strip()
    for line in rec["blockText"].splitlines():
        line = line.replace("​", "").strip()
        if line and line not in ("Contact Information",) and "@" not in line: return line
    return None

def group_of(page, rec):
    if rec["inHeader"]: return "site"
    cat = rec["precedingHeading"] or ""
    if page == "research": return "research"
    if page == "home":
        return "sponsors" if cat in ("Sponsors",) or rec["docY"] > 1300 else "gallery"
    if page in ("team-contact", "principal-investigator"):
        if cat in ("Principal Investigator", "Personal Profile", "Team & Contact") or page == "principal-investigator": return "pi"
        if cat in ALUMNI: return "alumni"
        if cat in CURRENT: return "team"
    return "gallery"

def main():
    RAW.mkdir(parents=True, exist_ok=True)
    entries = []; by_sha = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for slug in PAGES:
            url = BASE + slug
            page = br.new_page(viewport={"width": 1440, "height": 1000})
            got = {}
            def on_resp(r):
                if r.request.resource_type == "image" or "sitesv-images" in r.url:
                    try: got[r.url] = (r.status, r.headers.get("content-type", ""), r.body())
                    except Exception as e: got[r.url] = (r.status, "", None)
            page.on("response", on_resp)
            page.goto(url, wait_until="networkidle", timeout=90000)
            h = page.evaluate("document.body.scrollHeight")
            for y in range(0, h + 1500, 400): page.evaluate(f"scrollTo(0,{y})"); page.wait_for_timeout(200)
            page.wait_for_load_state("networkidle"); page.wait_for_timeout(2500)
            recs = page.evaluate(JS); page.close()
            print(slug, len(recs), "occurrences", file=sys.stderr)
            for i, rec in enumerate(recs):
                src = rec["src"]
                e = {"id": f"{slug}#{i:03d}", "originalPageUrl": url, "originalImageUrl": src, "occurrenceIndex": i,
                     "kind": rec["kind"], "alt": rec["alt"], "inHeader": rec["inHeader"],
                     "contentSection": rec["precedingHeading"], "associatedName": name_of(rec),
                     "domBlockHeadings": rec["blockHeadings"], "domBlockTextExcerpt": rec["blockText"][:400],
                     "domBlockLinks": rec["blockLinks"], "renderedSize": [rec["renderedWidth"], rec["renderedHeight"]],
                     "position": [rec["docX"], rec["docY"]],
                     "originalDimensions": [rec.get("naturalWidth"), rec.get("naturalHeight")] if rec["kind"] == "img" else None,
                     "group": group_of(slug, rec)}
                if src.startswith("data:") or not src.startswith("http"):
                    e.update(downloadStatus="skipped-non-http", verificationStatus="not-applicable"); entries.append(e); continue
                bstatus, bctype, bbytes = got.get(src, (None, "", None))
                e["browserCaptured"] = bbytes is not None
                # independent re-download of the exact signed URL the page served
                try:
                    r = requests.get(src, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
                    dl = r.content if r.ok else None; e["httpStatus"] = r.status_code; e["contentType"] = r.headers.get("content-type")
                except Exception as ex:
                    dl = None; e["httpError"] = repr(ex)
                data = bbytes or dl
                e["resolvedDownloadUrl"] = src
                e["recoveryMethod"] = ("browser-response-capture + independent HTTP re-download" if bbytes and dl
                                       else "browser-response-capture" if bbytes else "HTTP download" if dl else "none")
                if not data:
                    e.update(downloadStatus="failed", verificationStatus="unresolved"); entries.append(e); continue
                e["sha256BrowserBytes"] = hashlib.sha256(bbytes).hexdigest() if bbytes else None
                e["sha256HttpBytes"] = hashlib.sha256(dl).hexdigest() if dl else None
                e["bytesIdentical"] = (e["sha256BrowserBytes"] == e["sha256HttpBytes"]) if bbytes and dl else None
                try:
                    im = Image.open(io.BytesIO(data)); im.load(); fmt = im.format; size = list(im.size)
                except Exception as ex:
                    e.update(downloadStatus="corrupt", verificationStatus="failed", decodeError=repr(ex)); entries.append(e); continue
                sha = hashlib.sha256(data).hexdigest(); ext = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp", "MPO": "jpg"}.get(fmt, fmt.lower())
                (RAW / f"{sha}.{ext}").write_bytes(data)
                e.update(sha256=sha, fileSize=len(data), format=fmt, downloadedDimensions=size, downloadStatus="ok",
                         servedSizeSuffix=src.rsplit("=", 1)[-1] if "=" in src else None,
                         possiblyDownscaledByHost=(size[0] == 1280 and src.endswith("=w1280")))
                entries.append(e)
        br.close()

    # Assign local destinations. Identical bytes => one file; first semantically-strongest owner names it.
    rank = {"pi": 0, "team": 1, "alumni": 2, "research": 3, "sponsors": 4, "gallery": 5, "site": 6}
    for e in sorted([e for e in entries if e.get("sha256")], key=lambda e: (rank[e["group"]], e["id"])):
        sha = e["sha256"]
        if sha in by_sha:
            e["localPath"] = by_sha[sha]; e["duplicateOfFirstOccurrence"] = True; continue
        g = e["group"]
        if g in ("pi", "team", "alumni"): stem = slugify(e["associatedName"])
        elif g == "research": stem = "research-" + slugify(e["contentSection"] if e["contentSection"] != "Research Areas" or not e["associatedName"] else e["associatedName"])[:60]
        elif g == "site": stem = ("site-logo" if e["kind"] == "img" else "banner-" + e["originalPageUrl"].rsplit("/", 1)[-1])
        else: stem = f"{g}-{sha[:10]}"
        if g == "research" and e["associatedName"]: stem = "research-" + slugify(e["associatedName"])[:60]
        rel = f"{g}/{stem}." + {'JPEG': 'jpg', 'MPO': 'jpg'}.get(e['format'], e['format'].lower())
        n = 2
        while rel in by_sha.values(): rel = f"{g}/{stem}-{n}.{rel.rsplit('.', 1)[1]}"; n += 1
        (PUB / g).mkdir(parents=True, exist_ok=True)
        (PUB / rel).write_bytes(next(RAW.glob(sha + ".*")).read_bytes())
        by_sha[sha] = rel; e["localPath"] = rel; e["duplicateOfFirstOccurrence"] = False
    for e in entries:
        if e.get("localPath"): e["localFile"] = "public/assets/" + e["localPath"]; e["localFilename"] = e["localPath"].rsplit("/", 1)[1]
    man = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "site": BASE,
           "notes": ["Google Sites serves signed per-size URLs; only the served suffix (=w1280 for content, =w16383 for logo) is retrievable (other suffixes return 403). "
                     "Images whose served width is exactly 1280 may be host-downscaled versions of larger uploads; no larger public variant exists."],
           "occurrenceCount": len(entries), "uniqueImages": len(by_sha), "entries": entries}
    (MIG / "image-manifest.json").write_text(json.dumps(man, indent=1, ensure_ascii=False))
    from collections import Counter
    print("occurrences", len(entries), "unique", len(by_sha), Counter(e["group"] for e in entries), Counter(e.get("downloadStatus") for e in entries))

if __name__ == "__main__":
    main()
