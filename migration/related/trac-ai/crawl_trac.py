"""Archive https://trac-ai.iastate.edu/ (Translational AI Center, Iowa State).

Discovery: robots.txt (404 at crawl time -> no Disallow rules, but we still
honor any that appear), WordPress sitemaps, and same-host links in the
rendered DOM. Host-limited, <=300 pages, ~1 s delay, browser UA.
Outputs (relative to this file): pages/<slug>/{rendered.html,text.txt,
screenshot.jpg,page.json}, images/, inventory.json.
"""
import hashlib, io, json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
from urllib import robotparser
import requests
from bs4 import BeautifulSoup
from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGES = HERE / "pages"; IMAGES = HERE / "images"
HOST = "trac-ai.iastate.edu"; BASE = f"https://{HOST}/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MAX_PAGES = 300; DELAY = 1.0; DISK_CAP = 150 * 1024 * 1024
SKIP_RE = re.compile(r"/(wp-admin|wp-login|wp-json|feed|xmlrpc|wp-content|wp-includes|my-bookings|cart|checkout)(/|$)|"
                     r"\.(pdf|docx?|xlsx?|pptx?|zip|jpe?g|png|gif|svg|webp|mp4|ics)$|"
                     # The Events Calendar generates unbounded date/view permutations; skip them
                     r"/events/(.+/)?(month|list|day|week|photo|map|summary|today)/|/events/(.+/)?\d{4}-\d{2}(-\d{2})?/", re.I)
S = requests.Session(); S.headers["User-Agent"] = UA

EXTRACT_JS = r"""
() => {
  const out = {blocks: [], images: [], links: [], embeds: [], headings: []};
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && (r.width > 0 || r.height > 0); };
  let order = 0, lastHeading = null;
  const blockText = el => { const b = el.closest('figure, li, article, .wp-block-column, .wp-block-group, .wp-block-media-text, .elementor-widget-wrap, section, div');
    return b ? b.innerText.trim().replace(/\s+/g,' ').slice(0, 400) : ''; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = walker.nextNode())) {
    const tag = n.tagName.toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'noscript') continue;
    if (/^h[1-6]$/.test(tag)) {
      const t = n.innerText.trim(); if (t) { lastHeading = t; out.headings.push({level: tag, text: t, order});
        out.blocks.push({kind: 'heading', level: tag, text: t, order: order++}); }
    } else if (['p','li','blockquote','figcaption','td','dt','dd'].includes(tag)) {
      const t = n.innerText.trim();
      if (t && !n.parentElement.closest('p,li,blockquote,figcaption,td,dt,dd'))
        out.blocks.push({kind: tag, text: t, order: order++, inNav: !!n.closest('nav,header,footer')});
    } else if (tag === 'img') {
      const r = n.getBoundingClientRect(); const a = n.closest('a');
      const rec = {kind: 'img', src: n.currentSrc || n.src, srcAttr: n.getAttribute('src'),
        dataSrc: n.getAttribute('data-src') || n.getAttribute('data-lazy-src'), srcset: n.getAttribute('srcset') || n.getAttribute('data-srcset'),
        alt: n.alt, naturalWidth: n.naturalWidth, naturalHeight: n.naturalHeight,
        renderedWidth: Math.round(r.width), renderedHeight: Math.round(r.height), visible: vis(n),
        linkHref: a ? a.href : null, nearestHeading: lastHeading, blockText: blockText(n),
        inHeader: !!n.closest('header'), inFooter: !!n.closest('footer'), inNav: !!n.closest('nav'), order: order++};
      out.images.push(rec); out.blocks.push({kind: 'image', src: rec.src, alt: rec.alt, order: rec.order});
    } else if (['iframe','embed','object','video','audio'].includes(tag)) {
      out.embeds.push({tag, src: n.src || n.getAttribute('data') || n.getAttribute('data-src') || '', title: n.title || '', order: order++});
      out.blocks.push({kind: 'embed', src: n.src, order: order - 1});
    }
    const bg = getComputedStyle(n).backgroundImage;
    if (bg && bg !== 'none' && bg.includes('url(') && tag !== 'img') {
      for (const u of (bg.match(/url\("?([^")]+)"?\)/g) || [])) { const url = u.replace(/^url\("?|"?\)$/g, '');
        out.images.push({kind: 'css-background', src: url, element: tag, nearestHeading: lastHeading, blockText: n.innerText ? n.innerText.trim().replace(/\s+/g,' ').slice(0,400) : '',
          visible: vis(n), inHeader: !!n.closest('header'), inFooter: !!n.closest('footer'), order: order++}); }
    }
  }
  document.querySelectorAll('a[href]').forEach(a => out.links.push({href: a.href, text: a.innerText.trim().replace(/\s+/g,' '), inNav: !!a.closest('nav,header,footer')}));
  out.title = document.title; out.text = document.body.innerText;
  return out;
}
"""

def norm(url):
    url = urldefrag(url)[0]
    p = urlparse(url)
    if p.scheme not in ("http", "https") or p.netloc.lower() not in (HOST, "www." + HOST): return None
    if p.query: return None  # query-string views (calendar filters, ical, search) are skipped
    path = p.path or "/"
    if not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]: path += "/"
    return f"https://{HOST}{path}"

def slug(url):
    s = urlparse(url).path.strip("/").replace("/", "__")
    return re.sub(r"[^A-Za-z0-9_.-]", "-", s) or "home"

def dir_size(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

def sitemap_urls():
    urls, todo, seen = [], [BASE + "wp-sitemap.xml"], set()
    while todo:
        sm = todo.pop(0)
        if sm in seen: continue
        seen.add(sm)
        try: r = S.get(sm, timeout=30); time.sleep(DELAY)
        except Exception as e: print("sitemap fail", sm, e, file=sys.stderr); continue
        if r.status_code != 200: continue
        soup = BeautifulSoup(r.text, "xml")
        for s in soup.select("sitemap > loc"): todo.append(s.text.strip())
        for u in soup.select("url > loc"): urls.append(u.text.strip())
    return urls, sorted(seen)

def main():
    PAGES.mkdir(parents=True, exist_ok=True); IMAGES.mkdir(exist_ok=True)
    rp = robotparser.RobotFileParser(); rr = S.get(BASE + "robots.txt", timeout=30)
    robots = {"status": rr.status_code, "body": rr.text if rr.status_code == 200 else None}
    rp.parse(rr.text.splitlines() if rr.status_code == 200 else [])
    allowed = lambda u: rp.can_fetch(UA, u) if rr.status_code == 200 else True
    sm_urls, sitemaps = sitemap_urls()
    queue = []; seen = set(); skipped = []
    for u in [BASE] + sm_urls:
        n = norm(u)
        if n and n not in queue: queue.append(n)
    inventory = []; stopped_early = None
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1440, "height": 1000}, user_agent=UA)
        page = ctx.new_page()
        while queue:
            if len(inventory) >= MAX_PAGES: stopped_early = f"page cap {MAX_PAGES}"; break
            if dir_size(HERE) > DISK_CAP * 0.8: stopped_early = "disk budget"; break
            url = queue.pop(0)
            if url in seen: continue
            seen.add(url)
            if SKIP_RE.search(urlparse(url).path) or not allowed(url): skipped.append(url); continue
            print(f"[{len(inventory)+1}] {url}", file=sys.stderr)
            rec = {"url": url, "slug": slug(url)}
            cached = PAGES / rec["slug"] / "page.json"
            if cached.exists():  # resume support: reuse an already-archived page
                rec = json.loads(cached.read_text())
                for l in rec["links"]["internal"]:
                    n = norm(l["href"])
                    if n and n not in seen and n not in queue: queue.append(n)
                inventory.append(rec); continue
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try: page.wait_for_load_state("networkidle", timeout=20000)
                except Exception: pass
                rec["httpStatus"] = resp.status if resp else None
                rec["finalUrl"] = page.url
                h = page.evaluate("document.body.scrollHeight")
                for y in range(0, min(h, 30000) + 1000, 600):
                    page.evaluate(f"window.scrollTo(0,{y})"); page.wait_for_timeout(200)
                try: page.wait_for_load_state("networkidle", timeout=10000)
                except Exception: pass
                page.evaluate("""() => Promise.all(Array.from(document.images).filter(i => !i.complete)
                    .map(i => new Promise(r => { i.onload = i.onerror = r; setTimeout(r, 5000); })))""")
                page.wait_for_timeout(500); page.evaluate("window.scrollTo(0,0)"); page.wait_for_timeout(300)
                data = page.evaluate(EXTRACT_JS)
                d = PAGES / rec["slug"]; d.mkdir(parents=True, exist_ok=True)
                (d / "rendered.html").write_text(page.content())
                (d / "text.txt").write_text(data["text"])
                page.screenshot(path=str(d / "screenshot.jpg"), full_page=True, type="jpeg", quality=70)
                internal, external = [], []
                for l in data["links"]:
                    n = norm(l["href"])
                    (internal if n else external).append(l)
                    if n and n not in seen and n not in queue: queue.append(n)
                rec.update(title=data["title"], headings=data["headings"], blocks=data["blocks"],
                           links={"internal": internal, "external": external}, images=data["images"], embeds=data["embeds"],
                           textLength=len(data["text"]), textSha256=hashlib.sha256(data["text"].encode()).hexdigest(),
                           archived=True, snapshot=f"pages/{rec['slug']}/")
                (d / "page.json").write_text(json.dumps(rec, indent=1))
            except Exception as e:
                rec["archived"] = False; rec["error"] = repr(e)
                print("  FAIL", e, file=sys.stderr)
            inventory.append(rec)
            time.sleep(DELAY)
        br.close()
    images, img_fail = download_images(inventory)
    out = {"site": BASE, "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "robots": robots, "sitemaps": sitemaps,
           "sitemapUrlCount": len(sm_urls), "discoveryMethods": ["WordPress sitemaps", "same-host links in rendered DOM"],
           "stoppedEarly": stopped_early, "skippedUrls": skipped, "pageCount": len(inventory),
           "pageFailures": [{"url": p["url"], "error": p.get("error")} for p in inventory if not p.get("archived")],
           "pages": [{k: v for k, v in p.items() if k not in ("blocks",)} for p in inventory],
           "imageCount": sum(1 for i in images if i["status"] == "ok"), "imageFailures": img_fail, "images": images,
           "diskBytes": dir_size(HERE)}
    (HERE / "inventory.json").write_text(json.dumps(out, indent=1))
    print("pages", len(inventory), "images ok", out["imageCount"], "img failures", len(img_fail), "bytes", out["diskBytes"], file=sys.stderr)

WP_SIZE = re.compile(r"-(\d+)x(\d+)(\.[A-Za-z0-9]+)$")

def srcset_best(srcset, base):
    best, bw = None, -1
    for part in (srcset or "").split(","):
        bits = part.strip().split()
        if not bits: continue
        w = 0
        if len(bits) > 1:
            m = re.match(r"([\d.]+)([wx])", bits[1])
            if m: w = float(m.group(1)) * (1 if m.group(2) == "w" else 1000)
        if w > bw: best, bw = urljoin(base, bits[0]), w
    return best

def candidates(img, page_url):
    srcs = []
    best = srcset_best(img.get("srcset"), page_url)
    for s in [best, img.get("dataSrc") and urljoin(page_url, img["dataSrc"]), img.get("src")]:
        if not s or s.startswith("data:"): continue
        s = urldefrag(s)[0]
        p = urlparse(s); path = p.path
        if WP_SIZE.search(path):
            srcs.append(s.replace(path, WP_SIZE.sub(r"\3", path)))
        if "-scaled." in path:
            srcs.append(s.replace("-scaled.", "."))
        srcs.append(s)
    return list(dict.fromkeys(srcs))

def download_images(inventory):
    tracking = re.compile(r"(pixel|tracking|analytics|facebook\.com/tr|doubleclick|google-analytics|gravatar|spacer|blank\.gif)", re.I)
    groups = {}  # canonical key -> record
    for p in inventory:
        for img in p.get("images", []):
            src = img.get("src") or ""
            if not src or src.startswith("data:") or tracking.search(src): continue
            if img["kind"] == "img" and img.get("naturalWidth") and img.get("naturalHeight") and \
               (img["naturalWidth"] < 32 or img["naturalHeight"] < 32): continue
            cands = candidates(img, p["url"])
            key = cands[0] if cands else src
            g = groups.setdefault(key, {"candidates": cands, "sourcePages": [], "alt": set(), "nearestHeadings": set(),
                                        "kinds": set(), "blockText": img.get("blockText", "")})
            if p["url"] not in g["sourcePages"]: g["sourcePages"].append(p["url"])
            if img.get("alt"): g["alt"].add(img["alt"])
            if img.get("nearestHeading"): g["nearestHeadings"].add(img["nearestHeading"])
            g["kinds"].add(img["kind"])
    out, fails, by_sha = [], [], {}
    for key, g in groups.items():
        rec = {"key": key, "candidates": g["candidates"], "sourcePages": g["sourcePages"], "alt": sorted(g["alt"]),
               "nearestHeadings": sorted(g["nearestHeadings"]), "kinds": sorted(g["kinds"]), "blockText": g["blockText"]}
        if dir_size(HERE) > DISK_CAP: rec["status"] = "skipped-disk-cap"; out.append(rec); fails.append({"key": key, "reason": "disk cap"}); continue
        err = None
        for c in g["candidates"]:
            try:
                r = S.get(c, timeout=60); time.sleep(0.3)
                if r.status_code != 200: err = f"HTTP {r.status_code} {c}"; continue
                body = r.content
                ctype = r.headers.get("content-type", "")
                if "svg" in ctype or c.lower().endswith(".svg"):
                    rec.update(status="skipped-svg", url=c); break
                try:
                    im = Image.open(io.BytesIO(body)); im.verify()
                    im = Image.open(io.BytesIO(body)); im.load(); w, h = im.size; fmt = im.format
                except Exception as e:
                    err = f"corrupt/unreadable {c}: {e}"; continue
                if w < 32 or h < 32: rec.update(status="skipped-small", url=c, width=w, height=h); break
                sha = hashlib.sha256(body).hexdigest()
                rec.update(url=c, firstChoice=(c == g["candidates"][0]), width=w, height=h, format=fmt,
                           bytes=len(body), sha256=sha, verified=True)
                if sha in by_sha:
                    rec.update(status="duplicate", duplicateOf=by_sha[sha])
                else:
                    name = Path(urlparse(c).path).name or "image"
                    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
                    fn = IMAGES / f"{sha[:10]}_{name}"
                    fn.write_bytes(body); by_sha[sha] = f"images/{fn.name}"
                    rec.update(status="ok", file=f"images/{fn.name}")
                break
            except Exception as e:
                err = repr(e)
        if "status" not in rec:
            rec.update(status="failed", error=err); fails.append({"key": key, "error": err, "sourcePages": g["sourcePages"]})
        out.append(rec)
        print("img", rec["status"], rec.get("url", key), file=sys.stderr)
    return out, fails

if __name__ == "__main__":
    main()
