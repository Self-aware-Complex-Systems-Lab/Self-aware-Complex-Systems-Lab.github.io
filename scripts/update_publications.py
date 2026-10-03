"""Pull new publications into the site (run weekly by .github/workflows/update-publications.yml).

Sources (public scholarly APIs, queried by ORCID 0000-0002-6775-9199, Prof. Soumik Sarkar):
  1. OpenAlex  https://api.openalex.org   (indexes journals, conferences, arXiv and other repositories)
  2. Crossref  https://api.crossref.org   (DOI registrations listing the ORCID)
Google Scholar offers no API and blocks automated access, so it is not queried; OpenAlex covers the same literature.

New items (not already listed by DOI, exact title, or near-identical title with the same first author) are appended to
src/data/publications-added.json. Then duplicate detection and per-person publication lists are regenerated.
Only the Python standard library is used. Exit code 0 always; prints a summary.
"""
import datetime as dt
import difflib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "src/data"
ORCID = "0000-0002-6775-9199"
LOOKBACK_YEARS = 3
UA = {"User-Agent": "scslab-website-updater (https://self-aware-complex-systems-lab.github.io)"}
LABEL = {"journals": "Journal Articles", "conferences": "Conference Proceedings", "preprints": "Preprints"}
SKIP_TITLE = re.compile(r"^(correction|erratum|retraction|editorial|front matter|back matter|table of contents|author correction)\b", re.I)


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


norm = lambda t: re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (t or "").lower())).strip()


def first_surname(authors):
    a = re.split(r"\s+and\s+|,\s*", authors or "")[0].strip()
    return a.split()[-1].lower() if a else ""


def openalex_items():
    since = (dt.date.today() - dt.timedelta(days=365 * LOOKBACK_YEARS)).isoformat()
    out, cursor = [], "*"
    while cursor:
        d = get_json(f"https://api.openalex.org/works?filter=authorships.author.orcid:{ORCID},from_publication_date:{since}"
                     f"&per-page=200&cursor={cursor}")
        for w in d["results"]:
            if not w.get("title") or SKIP_TITLE.match(w["title"]) or w.get("type") in ("paratext", "dataset", "erratum", "editorial", "letter", "peer-review"):
                continue
            src = (w.get("primary_location") or {}).get("source") or {}
            st, wt = src.get("type"), w.get("type")
            cat = ("preprints" if wt == "preprint" or st == "repository" else
                   "conferences" if st == "conference" or wt == "proceedings-article" else "journals")
            doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
            venue = re.sub(r"\barXiv\s*\(Cornell University\)", "arXiv", src.get("display_name") or "", flags=re.I) or None  # plain "arXiv"
            out.append({"category": cat, "categoryLabel": LABEL[cat], "number": None, "title": re.sub(r"\s+", " ", w["title"]).strip(),
                        "authors": " and ".join(a["author"]["display_name"] for a in w["authorships"]),
                        "venue": venue, "year": w.get("publication_year"), "date": w.get("publication_date"),
                        "type": wt, "citationsAsOfArchive": None, "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url"),
                        "doi": doi, "source": f"OpenAlex (auto, {dt.date.today()})", "openalex": w["id"]})
        cursor = d["meta"].get("next_cursor") if d["results"] else None
    return out


def crossref_items():
    since = (dt.date.today() - dt.timedelta(days=365 * LOOKBACK_YEARS)).isoformat()
    d = get_json(f"https://api.crossref.org/works?filter=orcid:{ORCID},from-pub-date:{since}&rows=200")
    out = []
    for w in d["message"]["items"]:
        title = re.sub(r"\s+", " ", (w.get("title") or [""])[0]).strip()
        if not title or SKIP_TITLE.match(title) or w.get("type") in ("peer-review", "component", "dataset"):
            continue
        wt = w.get("type")
        cat = "preprints" if wt == "posted-content" else "conferences" if wt == "proceedings-article" else "journals"
        parts = (w.get("published") or w.get("issued") or {}).get("date-parts", [[None]])[0]
        yr = parts[0] if parts else None
        date = "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts)) if parts and len(parts) == 3 else None
        authors = " and ".join(" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in w.get("author", []))
        venue = (w.get("container-title") or [None])[0]
        out.append({"category": cat, "categoryLabel": LABEL[cat], "number": None, "title": title, "authors": authors or None,
                    "venue": venue, "year": yr, "date": date, "type": wt, "citationsAsOfArchive": None,
                    "url": f"https://doi.org/{w['DOI']}", "doi": w["DOI"], "source": f"Crossref (auto, {dt.date.today()})"})
    return out


def refresh_metadata():
    """Citation metrics + corresponding authors for the vita (src/data/scholar-metrics.json, src/data/pub-meta.json)."""
    authors = get_json(f"https://api.openalex.org/authors?filter=orcid:{ORCID}&per-page=25")["results"]
    main_author = max(authors, key=lambda a: a.get("works_count", 0))
    st = main_author.get("summary_stats") or {}
    (D / "scholar-metrics.json").write_text(json.dumps({
        "source": "OpenAlex", "author": main_author["id"], "collected": dt.date.today().isoformat(),
        "citations": main_author.get("cited_by_count"), "hIndex": st.get("h_index"), "i10Index": st.get("i10_index"),
        "works": main_author.get("works_count")}, indent=1) + "\n")
    meta, cursor = {}, "*"
    while cursor:
        d = get_json(f"https://api.openalex.org/works?filter=authorships.author.orcid:{ORCID}&per-page=200&cursor={cursor}"
                     "&select=id,title,doi,authorships,corresponding_author_ids,publication_year")
        for w in d["results"]:
            if not w.get("title"): continue
            ids = set(w.get("corresponding_author_ids") or [])
            corr = [a["author"]["display_name"] for a in w.get("authorships", []) if a["author"]["id"] in ids or a.get("is_corresponding")]
            if corr:
                meta[norm(w["title"]).replace(" ", "")] = {"corresponding": corr, "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None}
        cursor = d["meta"].get("next_cursor") if d["results"] else None
    (D / "pub-meta.json").write_text(json.dumps({"source": "OpenAlex corresponding_author_ids", "collected": dt.date.today().isoformat(),
                                                  "byTitle": meta}, indent=1, ensure_ascii=False) + "\n")
    return f"metrics + corresponding authors for {len(meta)} works"


def main():
    archived = json.loads((D / "publications.json").read_text())
    added_path = D / "publications-added.json"
    added = json.loads(added_path.read_text())
    existing = archived + added
    titles = {norm(p["title"]) for p in existing}
    dois = {(p.get("doi") or "").lower() for p in existing if p.get("doi")}
    by_len = [(norm(p["title"]), first_surname(p.get("authors"))) for p in existing]

    def is_known(c):
        t = norm(c["title"])
        if t in titles or (c.get("doi") and c["doi"].lower() in dois):
            return True
        fs = first_surname(c.get("authors"))
        return any(abs(len(t) - len(e)) < 20 and fa == fs and difflib.SequenceMatcher(None, t, e).ratio() >= 0.9 for e, fa in by_len)

    report = {}
    new = []
    for name, fetch in (("OpenAlex", openalex_items), ("Crossref", crossref_items)):
        try:
            items = fetch()
        except Exception as e:  # a source being down must not break the site update
            report[name] = f"failed: {e!r}"
            continue
        fresh = [c for c in items if not is_known(c)]
        for c in fresh:  # make later candidates see earlier additions
            titles.add(norm(c["title"]))
            if c.get("doi"): dois.add(c["doi"].lower())
            by_len.append((norm(c["title"]), first_surname(c.get("authors"))))
        new += fresh
        report[name] = f"{len(items)} fetched, {len(fresh)} new"

    if new:
        # Append (never prepend): other data files reference entries by their index ("added:<i>").
        new.sort(key=lambda p: (p.get("date") or str(p.get("year") or 0)))
        added_path.write_text(json.dumps(added + new, indent=1, ensure_ascii=False) + "\n")
    # Re-key-sensitive derived data: duplicates and per-person lists
    for script in ("migration/scripts/dedupe_pubs.py", "migration/scripts/person_pubs.py"):
        subprocess.run([sys.executable, str(ROOT / script)], check=True, capture_output=True)
    try:
        report["metadata"] = refresh_metadata()
    except Exception as e:
        report["metadata"] = f"failed: {e!r}"
    print(json.dumps(report))
    for p in new:
        print(f"+ [{p['category']}] {p.get('year')} {p['title'][:100]}")
    print(f"{len(new)} new publications added")


if __name__ == "__main__":
    main()
