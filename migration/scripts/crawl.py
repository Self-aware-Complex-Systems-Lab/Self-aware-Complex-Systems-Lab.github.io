"""Phase 1: crawl the original SCSLab Google Site with Playwright.

For every page reachable under /view/scslab-isu/ this records: URL, title,
full text, headings, ordered content blocks (text + images in DOM order),
links, embeds, and saves a rendered HTML snapshot + full-page screenshot.
Output: migration/page-inventory.json, migration/archive/<slug>/...
"""
import json, re, sys, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "archive"
BASE = "https://sites.google.com/view/scslab-isu/"
SEEDS = [BASE + p for p in ["home", "team-contact", "principal-investigator", "publications"]]

# Walk the rendered DOM in document order, emitting text blocks, headings and
# images so text<->image association (e.g. a portrait next to a name) survives.
EXTRACT_JS = r"""
() => {
  const out = {blocks: [], images: [], links: [], embeds: [], headings: []};
  const main = document.body;
  const seenImg = new Set();
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && (r.width > 0 || r.height > 0); };
  let order = 0;
  // Sections: Google Sites wraps each horizontal section in <section> elements.
  const sections = Array.from(main.querySelectorAll('section'));
  const secIndex = el => { for (let i = 0; i < sections.length; i++) if (sections[i].contains(el)) return i; return -1; };
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = walker.nextNode())) {
    const tag = n.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag) || n.getAttribute('role') === 'heading') {
      const t = n.innerText.trim(); if (t) { out.headings.push({level: tag, text: t, order}); out.blocks.push({kind: 'heading', text: t, order: order++, section: secIndex(n)}); }
    } else if (tag === 'p' || (tag === 'li')) {
      const t = n.innerText.trim(); if (t && !n.closest('h1,h2,h3,h4,h5,h6')) out.blocks.push({kind: tag === 'li' ? 'list-item' : 'paragraph', text: t, order: order++, section: secIndex(n)});
    } else if (tag === 'img') {
      const r = n.getBoundingClientRect();
      const a = n.closest('a');
      const rec = {kind: 'img', src: n.currentSrc || n.src, srcAttr: n.getAttribute('src'), srcset: n.getAttribute('srcset'),
        alt: n.alt, naturalWidth: n.naturalWidth, naturalHeight: n.naturalHeight, renderedWidth: Math.round(r.width), renderedHeight: Math.round(r.height),
        visible: vis(n), linkHref: a ? a.href : null, order: order++, section: secIndex(n), inHeader: !!n.closest('header'), inNav: !!n.closest('nav')};
      out.images.push(rec); out.blocks.push({kind: 'image', src: rec.src, order: rec.order, section: rec.section});
    } else if (tag === 'iframe' || tag === 'embed' || tag === 'object' || tag === 'video') {
      out.embeds.push({tag, src: n.src || n.getAttribute('data') || '', title: n.title || '', order: order++, section: secIndex(n)});
      out.blocks.push({kind: 'embed', src: n.src, order: order - 1, section: secIndex(n)});
    }
    const bg = getComputedStyle(n).backgroundImage;
    if (bg && bg !== 'none' && bg.includes('url(')) {
      const m = bg.match(/url\("?([^")]+)"?\)/g) || [];
      for (const u of m) { const url = u.replace(/^url\("?|"?\)$/g, '');
        out.images.push({kind: 'css-background', src: url, element: tag, cls: n.className && n.className.toString().slice(0, 80), order: order++, section: secIndex(n), inHeader: !!n.closest('header'), visible: vis(n)}); }
    }
  }
  document.querySelectorAll('a[href]').forEach(a => out.links.push({href: a.href, text: a.innerText.trim(), inNav: !!a.closest('nav, header [role=navigation]')}));
  out.title = document.title;
  out.text = main.innerText;
  out.sectionCount = sections.length;
  return out;
}
"""

def slug(url):
    p = urlparse(url).path.rstrip("/").split("/view/scslab-isu")[-1].strip("/")
    return p.replace("/", "__") or "root"

def norm(url):
    url = urldefrag(url)[0].split("?")[0].rstrip("/")
    return url

def main():
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    queue = list(SEEDS); seen = set(); inventory = []
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1440, "height": 1000}, user_agent=
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36")
        page = ctx.new_page()
        net_images = {}
        page.on("response", lambda r: net_images.setdefault(page.url, []).append(
            {"url": r.url, "status": r.status, "ctype": r.headers.get("content-type", "")})
            if r.request.resource_type == "image" else None)
        while queue:
            url = norm(queue.pop(0))
            if url in seen: continue
            seen.add(url)
            print("crawl", url, file=sys.stderr)
            rec = {"url": url, "slug": slug(url)}
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=60000)
                rec["httpStatus"] = resp.status if resp else None
                rec["finalUrl"] = page.url
                # progressive scroll for lazy images
                h = page.evaluate("document.body.scrollHeight")
                for y in range(0, h + 1200, 500):
                    page.evaluate(f"window.scrollTo(0,{y})"); page.wait_for_timeout(250)
                page.wait_for_load_state("networkidle"); page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0,0)")
                data = page.evaluate(EXTRACT_JS)
                d = ARCHIVE / rec["slug"]; d.mkdir(parents=True, exist_ok=True)
                (d / "rendered.html").write_text(page.content())
                (d / "text.txt").write_text(data["text"])
                page.screenshot(path=str(d / "screenshot.png"), full_page=True)
                rec.update({k: data[k] for k in ["title", "headings", "blocks", "images", "embeds", "links", "sectionCount"]})
                rec["textLength"] = len(data["text"]); rec["textSha256"] = hashlib.sha256(data["text"].encode()).hexdigest()
                rec["networkImages"] = net_images.get(page.url, [])
                rec["archived"] = True; rec["snapshot"] = f"migration/archive/{rec['slug']}/"
                for l in data["links"]:
                    h2 = norm(l["href"])
                    if h2.startswith(BASE.rstrip("/")) and h2 not in seen: queue.append(h2)
            except Exception as e:
                rec["archived"] = False; rec["error"] = repr(e)
            inventory.append(rec)
        br.close()
    out = {"site": BASE, "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seeds": SEEDS,
           "discoveryMethods": ["seed URLs", "navigation + in-page links (rendered DOM)"],
           "pageCount": len(inventory), "pages": inventory}
    (ROOT / "page-inventory.json").write_text(json.dumps(out, indent=2))
    print(json.dumps([(p["url"], p.get("title"), p.get("textLength"), len(p.get("images", []))) for p in inventory], indent=1))

if __name__ == "__main__":
    main()
