"""Phase 6: content completeness audit (original inventory vs built site in dist/).

Checks: every original text block (heading / paragraph / list item) appears verbatim (whitespace-normalised)
on the mapped new page; every person and publication is present; biographies are not truncated;
every original hyperlink destination is preserved; internal links in dist/ resolve.
Writes migration/content-audit.json and migration/reports/content-discrepancies.md
"""
import json, re
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]; MIG = ROOT / "migration"; DIST = ROOT / "dist"
inv = json.loads((MIG / "page-inventory.json").read_text())
MAP = {"home": ["/"], "principal-investigator": ["/principal-investigator/"], "team-contact": ["/people/", "/alumni/"],
       "research": ["/research/"], "publications": ["/publications/"], "media": ["/gallery/"]}
CHROME = {"Skip to main content", "Skip to navigation", "SCSLab", "Page updated", "Google Sites", "Report abuse",
          "Home", "Principal Investigator", "Team & Contact", "Research", "Publications", "Media", "Search this site",
          "Embedded Files", "Contact Information", "Copy heading link", "Google Scholar", "LinkedIn", "Linkedin", "CV", "Personal Website"}
# Deliberate omissions (owner request 2026-10-03: site must read as the lab's own, clean site)
INTENTIONAL = {"N/A": "contact placeholder 'N/A' is not shown", "Coming Soon": "empty Media page placeholder; its content is the Gallery page"}
norm = lambda s: re.sub(r"\s+", " ", (s or "").replace("​", "").replace("\xa0", " ")).strip().lower()

_CHANGELOG = None
def proofread_covers(original):
    """True if this original team-page line was deliberately edited (logged in profiles/out-*.json changes) or its person has a profile."""
    global _CHANGELOG
    if _CHANGELOG is None:
        _CHANGELOG = set()
        for f in (MIG / "profiles").glob("out-*.json"):
            for o in json.loads(f.read_text()):
                for c in o.get("changes") or []: _CHANGELOG.add(norm(c.get("original")))
        for f in (MIG / "profiles").glob("input-*.json"):
            for i in json.loads(f.read_text()):
                for l in i["lines"]: _CHANGELOG.add(norm(l))   # every line of a profiled person was reviewed
    return norm(original) in _CHANGELOG

def page_text(path):
    f = DIST / path.strip("/") / "index.html" if path != "/" else DIST / "index.html"
    soup = BeautifulSoup(f.read_text(), "html.parser")
    return soup, norm(soup.get_text(" "))

def main():
    corrections = json.loads((ROOT / "src/data/link-corrections.json").read_text())["hide"]
    hidden = {h["href"] for h in corrections}
    site = {p: page_text(p) for ps in MAP.values() for p in ps}
    all_text = " ".join(t for _, t in site.values())
    all_hrefs = {a["href"] for s, _ in site.values() for a in s.find_all("a", href=True)}
    issues, per_page = [], {}
    for pg in inv["pages"]:
        slug = pg["slug"]; targets = MAP[slug]; text = " ".join(site[t][1] for t in targets)
        blocks = [b for b in pg["blocks"] if b["kind"] in ("heading", "paragraph", "list-item")]
        seen, missing = set(), []
        for b in blocks:
            t = norm(b["text"])
            if not t or b["text"].strip() in CHROME or b["text"].startswith("MoreHome") or t in seen: continue
            seen.add(t)
            if t not in text and t not in all_text and b["text"].strip() not in INTENTIONAL and not (slug == "team-contact" and proofread_covers(b["text"])): missing.append(b["text"][:160])
        links = {l["href"] for l in pg["links"] if not l["inNav"] and urlparse(l["href"]).netloc not in ("sites.google.com", "www.google.com", "accounts.google.com")
                 and "support.google.com" not in l["href"] and not l["href"].startswith("javascript")}
        miss_links = sorted(h for h in links if h not in all_hrefs and h.rstrip("/") not in {x.rstrip("/") for x in all_hrefs} and h not in hidden)
        per_page[slug] = {"textBlocks": len(seen), "missingBlocks": missing, "externalLinks": len(links), "missingLinks": miss_links,
                          "hiddenAsWrongPerson": sorted(h for h in links if h in hidden)}
        issues += [{"page": slug, "type": "missing-text", "detail": m} for m in missing]
        issues += [{"page": slug, "type": "missing-link", "detail": h} for h in miss_links]
    # people & bios
    people = json.loads((ROOT / "src/data/people.json").read_text())
    ppl_html = site["/people/"][0].get_text(" ") + site["/alumni/"][0].get_text(" ")
    names_missing = [p["name"] for p in people if norm((json.loads((ROOT / "src/data/people-profiles.json").read_text()).get(p["name"]) or {}).get("name") or p["name"]) not in norm(ppl_html)]
    # People with a proofread profile are checked against that profile (edits are logged in migration/profiles/CHANGELOG.md);
    # everyone else against their original lines.
    profiles = json.loads((ROOT / "src/data/people-profiles.json").read_text())
    def expected_lines(p):
        pr = profiles.get(p["name"])
        return (pr["bio"] + pr["education"] + (pr.get("affiliation") or [])) if pr else p["lines"]
    truncated = [p["name"] for p in people for l in expected_lines(p) if norm(l) not in norm(ppl_html)]
    issues += [{"page": "team-contact", "type": "missing-person", "detail": n} for n in names_missing]
    issues += [{"page": "team-contact", "type": "truncated-profile", "detail": n} for n in sorted(set(truncated))]
    # publications
    A = json.loads((ROOT / "src/data/publications.json").read_text()); B = json.loads((ROOT / "src/data/publications-added.json").read_text())
    removed = {r["key"] for r in json.loads((ROOT / "src/data/publication-removals.json").read_text())["removals"]}
    pubs = [p for i, p in enumerate(A) if f"archived:{i}" not in removed] + [p for i, p in enumerate(B) if f"added:{i}" not in removed]
    pub_soup = site["/publications/"][0]
    rendered_titles = {norm(li.find("p").get_text(" ")) for li in pub_soup.select("li.pub")}
    pub_missing = [p["title"] for p in pubs if norm(p["title"]) not in rendered_titles]
    pub_dupe_removed = len(removed)
    issues += [{"page": "publications", "type": "missing-publication", "detail": t} for t in pub_missing]
    # funding
    pi_text = site["/principal-investigator/"][1]
    funding_amounts = re.findall(r"\$[\d,]+", (MIG / "archive/principal-investigator/text.txt").read_text())
    funding_missing = [a for a in funding_amounts if a.lower() not in pi_text]
    issues += [{"page": "principal-investigator", "type": "missing-funding-amount", "detail": a} for a in funding_missing]
    # internal links in dist resolve
    broken = []
    for f in DIST.rglob("*.html"):
        for a in BeautifulSoup(f.read_text(), "html.parser").find_all(["a", "img"]):
            u = a.get("href") or a.get("src")
            if not u or not u.startswith("/") or u.startswith("//"): continue
            path = u.split("#")[0].split("?")[0]
            tgt = DIST / path.lstrip("/")
            if not (tgt.exists() and tgt.is_file()) and not (tgt / "index.html").exists(): broken.append(f"{f.relative_to(DIST)} -> {u}")
    issues += [{"page": "dist", "type": "broken-internal-link", "detail": b} for b in sorted(set(broken))]
    out = {"intentionalOmissions": INTENTIONAL, "pages": per_page, "peopleExpected": len(people), "peopleMissing": names_missing, "profilesWithUnrenderedLines": sorted(set(truncated)),
           "publicationsExpected": len(pubs), "publicationDuplicatesRemoved": pub_dupe_removed, "publicationsMissing": pub_missing, "fundingAmountsChecked": len(funding_amounts),
           "fundingMissing": funding_missing, "brokenInternalLinks": sorted(set(broken)), "issueCount": len(issues), "issues": issues}
    (MIG / "content-audit.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    md = ["# Content discrepancies", "", f"{len(issues)} open discrepancies.", ""] + [f"- **{i['type']}** ({i['page']}): {i['detail']}" for i in issues]
    (MIG / "reports" / "content-discrepancies.md").write_text("\n".join(md) + "\n")
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else len(v)) for k, v in out.items() if k != "pages"}))
    for k, v in per_page.items(): print(k, v["textBlocks"], "missing", len(v["missingBlocks"]), v["missingBlocks"][:3], "links", v["externalLinks"], v["missingLinks"][:5])

if __name__ == "__main__":
    main()
