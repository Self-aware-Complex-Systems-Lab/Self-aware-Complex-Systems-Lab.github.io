"""Find preprints that have since been accepted somewhere.

For every visible preprint with an arXiv id, read its arXiv record (author comments + journal reference) and look for
acceptance statements ("accepted at/to/by …", "to appear in …", a conference/workshop name with a year).
Prints candidates; with --write, records them in src/data/publication-venues.json (curated overrides read by the site).
Each override keeps the evidence string from arXiv so a human can verify it.

    python scripts/check_preprint_venues.py [--write]
"""
import json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "src/data"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
VENUE = re.compile(r"(accepted (?:at|to|by|for|in)|to appear (?:in|at)|published (?:in|at)|camera[- ]ready|in proceedings of|"
                   r"\b(?:CVPR|ICCV|ECCV|NeurIPS|NIPS|ICML|ICLR|AAAI|IJCAI|KDD|WACV|ICRA|IROS|CoRL|RSS|ACC|CDC|L4DC|AISTATS|UAI|EMNLP|ACL|NAACL|MICCAI|ISBI)\b\s*'?\d{2,4})", re.I)


norm = lambda t: re.sub(r"[^a-z0-9]", "", (t or "").lower())


def arxiv_id(p):
    for s in (p.get("doi") or "", p.get("url") or ""):
        m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})|arxiv\.(\d{4}\.\d{4,5})", s, re.I)
        if m: return m.group(1) or m.group(2)
    return None


def arxiv_by_title(title):
    """Exact-title lookup on arXiv (normalised comparison) for preprints listed without an arXiv link."""
    q = urllib.parse.quote(f'ti:"{re.sub(r"[^A-Za-z0-9 ]", " ", title)[:200]}"')
    url = f"http://export.arxiv.org/api/query?search_query={q}&max_results=5"
    root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "scslab-site"}), timeout=60).read())
    for e in root.findall("a:entry", NS):
        if norm(e.findtext("a:title", "", NS)) == norm(title):
            return re.sub(r"v\d+$", "", e.find("a:id", NS).text.rsplit("/", 1)[-1])
    return None


def main():
    removed = {r["key"] for r in json.loads((D / "publication-removals.json").read_text())["removals"]}
    pubs = [(f"archived:{i}", p) for i, p in enumerate(json.loads((D / "publications.json").read_text()))] + \
           [(f"added:{i}", p) for i, p in enumerate(json.loads((D / "publications-added.json").read_text()))]
    cands = []
    for k, p in pubs:
        if k in removed or p["category"] != "preprints": continue
        aid = arxiv_id(p)
        if not aid:
            try: aid = arxiv_by_title(p["title"]); time.sleep(3)
            except Exception: aid = None
        if aid: cands.append((k, p, aid))
    found = []
    for i in range(0, len(cands), 40):
        batch = cands[i:i + 40]
        url = "http://export.arxiv.org/api/query?max_results=100&id_list=" + ",".join(c[2] for c in batch)
        root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "scslab-site"}), timeout=60).read())
        info = {}
        for e in root.findall("a:entry", NS):
            aid = re.sub(r"v\d+$", "", e.find("a:id", NS).text.rsplit("/", 1)[-1])
            info[aid] = {"comment": (e.findtext("arxiv:comment", "", NS) or "").strip(), "journal_ref": (e.findtext("arxiv:journal_ref", "", NS) or "").strip()}
        for k, p, aid in batch:
            r = info.get(aid, {})
            text = " ".join(x for x in (r.get("journal_ref"), r.get("comment")) if x)
            if r.get("journal_ref") or VENUE.search(text):
                found.append({"key": k, "title": p["title"], "arxiv": aid, "journalRef": r.get("journal_ref") or None, "comment": r.get("comment") or None})
        time.sleep(3)  # arXiv API etiquette
    print(f"{len(cands)} arXiv preprints checked; {len(found)} with acceptance/venue info")
    for f in found:
        print(f"- {f['key']} | {f['title'][:70]}\n    journal_ref: {f['journalRef']}\n    comment: {f['comment']}")
    if "--write" in sys.argv:
        (ROOT / "migration/publications-update/arxiv-venues.json").write_text(json.dumps(found, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
