"""Pull new publications into the site (run weekly by .github/workflows/update-publications.yml).

Sources (public scholarly APIs; settings in src/data/publication-sources.json):
  1. OpenAlex  https://api.openalex.org   (indexes journals, conferences, arXiv and other repositories), two routes:
     - works whose authorship carries Prof. Sarkar's ORCID 0000-0002-6775-9199
     - works of explicitly verified OpenAlex author IDs. OpenAlex sometimes files a new paper under a fresh author record
       without an ORCID, and the ORCID route then misses it. These IDs are a reviewed trust list, never discovered automatically.
  2. Crossref  https://api.crossref.org   (DOI registrations listing the ORCID)
Google Scholar offers no API and blocks automated access, so it is not queried; OpenAlex covers the same literature.

New items (not already listed by DOI, exact title, or near-identical title with the same first author) are appended to
src/data/publications-added.json. Then duplicate detection and per-person publication lists are regenerated.
Only the Python standard library is used.

Outcome (also written as JSON with --summary PATH):
  ok        every route and the metadata refresh succeeded                        exit 0, files written
  degraded  publications updated, but the optional metadata refresh failed        exit 0, metadata files left as they were
  partial   some required route failed                                            exit 1, nothing written
  failed    every required route failed, or derived data could not be rebuilt     exit 1, nothing written
Additions are all-or-nothing: if any route fails, nothing is written, so a short outage never commits half an update.
Existing entries are never removed or reordered.

    python scripts/update_publications.py [--summary PATH]
    python scripts/update_publications.py --review-candidates   # list unreviewed same-name OpenAlex author records
"""
import datetime as dt
import difflib
import email.utils
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "src/data"
UA = {"User-Agent": "scslab-website-updater (https://self-aware-complex-systems-lab.github.io)"}
LABEL = {"journals": "Journal Articles", "conferences": "Conference Proceedings", "preprints": "Preprints"}
SKIP_TITLE = re.compile(r"^(correction|erratum|retraction|editorial|front matter|back matter|table of contents|author correction)\b", re.I)
SKIP_TYPES = ("paratext", "dataset", "erratum", "editorial", "letter", "peer-review")
OPENALEX_SELECT = "id,title,doi,type,publication_year,publication_date,primary_location,authorships,corresponding_author_ids"
RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 4            # per request, so at most 3 retries
MAX_WAIT = 120          # seconds; a longer Retry-After (e.g. daily budget used up) fails at once instead of waiting
MAX_PAGES = 50          # per route; 200 works a page
DERIVED = ("publications-added.json", "publication-removals.json", "people-publications.json")


class SourceError(Exception):
    pass


def redact(url):
    return re.sub(r"(api_key=)[^&]+", r"\1***", url)


def retry_after(headers):
    v = (headers or {}).get("Retry-After")
    if not v:
        return None
    if v.strip().isdigit():
        return int(v)
    try:
        return max(0, (email.utils.parsedate_to_datetime(v) - dt.datetime.now(dt.timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def get_json(base, params, opener=urllib.request.urlopen, sleep=time.sleep):
    """GET base?params as JSON, retrying 429/5xx/timeouts a bounded number of times. Raises SourceError."""
    url = f"{base}?{urllib.parse.urlencode(params)}"
    for attempt in range(1, ATTEMPTS + 1):
        wait = 2 ** attempt
        try:
            with opener(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS:
                raise SourceError(f"HTTP {e.code} from {redact(url)}") from None
            ra = retry_after(e.headers)
            if ra is not None and ra > MAX_WAIT:
                raise SourceError(f"HTTP {e.code} from {redact(url)}; Retry-After {int(ra)} s is too long to wait") from None
            wait, err = (ra if ra is not None else wait), f"HTTP {e.code}"
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            err = f"network error {getattr(e, 'reason', e)!s}"
        except ValueError as e:
            raise SourceError(f"invalid JSON from {redact(url)}: {e}") from None
        if attempt < ATTEMPTS:
            sleep(wait)
    raise SourceError(f"{err} from {redact(url)} after {ATTEMPTS} attempts")


norm = lambda t: re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (t or "").lower())).strip()


def norm_doi(s):
    """'https://doi.org/10.48550/ARXIV.1', 'doi:10.48550/arxiv.1' -> '10.48550/arxiv.1'; None if not a DOI."""
    s = re.sub(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", "", (s or "").strip(), flags=re.I).lower()
    return s if s.startswith("10.") else None


def short_id(oa_id):
    return (oa_id or "").rsplit("/", 1)[-1]


def first_surname(authors):
    a = re.split(r"\s+and\s+|,\s*", authors or "")[0].strip()
    return a.split()[-1].lower() if a else ""


def load_config(path=None):
    cfg = json.loads(Path(path or D / "publication-sources.json").read_text())
    ids = [a["id"] for a in cfg.get("verifiedOpenAlexAuthorIds", [])]
    bad = [i for i in ids if not re.fullmatch(r"A\d+", i)] + [a["id"] for a in cfg.get("verifiedOpenAlexAuthorIds", []) if not a.get("evidence")]
    if bad or len(set(ids)) != len(ids) or set(ids) & {a["id"] for a in cfg.get("doNotTrust", [])}:
        raise SystemExit(f"publication-sources.json: verified IDs must be unique 'A<digits>' with evidence and not in doNotTrust ({bad or ids})")
    return cfg


def openalex_pages(fetch, filt):
    """Every work matching an OpenAlex filter (all years), following page numbers to the end.
    Page numbers, not cursors: since October 2026 OpenAlex answers keyless cursor paging past page 1 with HTTP 401.
    Page paging reaches 10,000 results, far above the ~500 works these routes return."""
    out, page, per = [], 1, 200
    while True:
        if page > MAX_PAGES:
            raise SourceError(f"OpenAlex pagination did not finish for {filt} after {MAX_PAGES} pages")
        params = {"filter": filt, "per-page": per, "page": page, "select": OPENALEX_SELECT}
        if os.environ.get("OPENALEX_API_KEY"):  # optional; never logged (see redact)
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        d = fetch("https://api.openalex.org/works", params)
        out += d["results"]
        if not d["results"] or len(out) >= d["meta"]["count"]:  # also correct if the API caps per-page lower
            break
        page += 1
    unique = {w["id"]: w for w in out}
    if len(unique) != d["meta"]["count"]:  # pages shifted while reading (no stable sort is offered); retry next run
        raise SourceError(f"OpenAlex returned {len(unique)} distinct works but reported {d['meta']['count']} for {filt}")
    return list(unique.values())


def openalex_routes(fetch, cfg):
    """Union of the ORCID route and the verified-author-ID route, deduplicated by work ID before conversion.
    Returns ({work id: (work, routes)}, [route reports])."""
    verified = [a["id"] for a in cfg.get("verifiedOpenAlexAuthorIds", [])]
    routes = [(f"orcid:{cfg['orcid']}", f"authorships.author.orcid:{cfg['orcid']}")]
    if verified:  # one OR-filter query for all verified IDs keeps the call count low
        routes.append(("openalex-author:" + "|".join(verified), "authorships.author.id:" + "|".join(verified)))
    works, reports = {}, []
    for route, filt in routes:
        rep = {"source": "OpenAlex", "route": route, "required": True}
        try:
            got = openalex_pages(fetch, filt)
        except (SourceError, KeyError, TypeError) as e:  # KeyError/TypeError: unexpected response shape
            reports.append(dict(rep, ok=False, fetched=None, error=str(e) if isinstance(e, SourceError) else f"unexpected response: {e!r}"))
            continue
        for w in got:
            if route.startswith("orcid:"):
                tags = {route}
            else:  # name the verified ID(s) that actually carry the work
                ids = {short_id((a.get("author") or {}).get("id")) for a in w.get("authorships", [])}
                tags = {f"openalex-author:{i}" for i in ids & set(verified)} or {route}
            w0, seen = works.get(w["id"], (w, []))
            works[w["id"]] = (w0, seen + sorted(tags - set(seen)))  # routes in query order: ORCID first
        reports.append(dict(rep, ok=True, fetched=len(got), error=None))
    return works, reports


def openalex_item(w, routes, today):
    src = (w.get("primary_location") or {}).get("source") or {}
    st, wt = src.get("type"), w.get("type")
    cat = ("preprints" if wt == "preprint" or st == "repository" else
           "conferences" if st == "conference" or wt in ("proceedings-article", "conference-paper") else "journals")
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    venue = re.sub(r"\barXiv\s*\(Cornell University\)", "arXiv", src.get("display_name") or "", flags=re.I) or None  # plain "arXiv"
    return {"category": cat, "categoryLabel": LABEL[cat], "number": None, "title": re.sub(r"\s+", " ", w["title"]).strip(),
            "authors": " and ".join(a["author"]["display_name"] for a in w["authorships"]),
            "venue": venue, "year": w.get("publication_year"), "date": w.get("publication_date"),
            "type": wt, "citationsAsOfArchive": None, "url": w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url"),
            "doi": doi, "source": f"OpenAlex (auto, {today})", "openalex": w["id"], "retrieval": routes}


def eligible_openalex(w, since):
    return (w.get("title") and not SKIP_TITLE.match(w["title"]) and w.get("type") not in SKIP_TYPES
            and (w.get("publication_date") or "") >= since)


def crossref_items(fetch, cfg, since, today):
    out, cursor, seen = [], "*", set()
    while cursor:
        if cursor in seen or len(seen) >= MAX_PAGES:
            raise SourceError(f"Crossref pagination did not finish after {len(seen)} pages")
        seen.add(cursor)
        msg = fetch("https://api.crossref.org/works", {"filter": f"orcid:{cfg['orcid']},from-pub-date:{since}", "rows": 200, "cursor": cursor})["message"]
        for w in msg["items"]:
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
                        "url": f"https://doi.org/{w['DOI']}", "doi": w["DOI"], "source": f"Crossref (auto, {today})",
                        "retrieval": [f"crossref-orcid:{cfg['orcid']}"]})
        cursor = msg.get("next-cursor") if msg["items"] else None
    return out


def metadata(fetch, cfg, works, today):
    """Citation metrics + corresponding authors for the vita (scholar-metrics.json, pub-meta.json); nothing is written here.
    Metrics come from the single largest ORCID-linked OpenAlex author record. They are not summed over fragmented records:
    h-index and i10 are not additive and the records share works. Corresponding authors come from OpenAlex's
    corresponding_author_ids / is_corresponding over the same work union as the publications, never from author order."""
    authors = fetch("https://api.openalex.org/authors", {"filter": f"orcid:{cfg['orcid']}", "per-page": 25})["results"]
    if not authors:
        raise SourceError(f"OpenAlex lists no author for ORCID {cfg['orcid']}")
    main_author = max(authors, key=lambda a: a.get("works_count", 0))
    st = main_author.get("summary_stats") or {}
    metrics = {"source": "OpenAlex", "author": main_author["id"], "collected": today,
               "citations": main_author.get("cited_by_count"), "hIndex": st.get("h_index"), "i10Index": st.get("i10_index"),
               "works": main_author.get("works_count")}
    meta = {}
    for w, _ in sorted(works.values(), key=lambda x: x[0]["id"]):  # stable order, whatever order the API pages in
        if not w.get("title"): continue
        ids = set(w.get("corresponding_author_ids") or [])
        corr = [a["author"]["display_name"] for a in w.get("authorships", []) if a["author"].get("id") in ids or a.get("is_corresponding")]
        if corr:
            meta[norm(w["title"]).replace(" ", "")] = {"corresponding": corr, "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None}
    pub_meta = {"source": "OpenAlex corresponding_author_ids", "collected": today, "byTitle": meta}
    return metrics, pub_meta, f"metrics from {short_id(main_author['id'])} ({len(authors)} ORCID-linked records, not summed) + corresponding authors for {len(meta)} works"


def run_derived(data_dir):
    if data_dir != D:  # the derived-data scripts only know the repository's own src/data
        return
    for script in ("migration/scripts/dedupe_pubs.py", "migration/scripts/person_pubs.py"):
        p = subprocess.run([sys.executable, str(ROOT / script)], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError(f"{script} exited {p.returncode}: {p.stderr.strip()[-500:]}")


def update(data_dir=D, cfg=None, fetch=get_json, today=None, derived=run_derived):
    """Run one update and return the summary dict (see module docstring)."""
    cfg = cfg or load_config(data_dir / "publication-sources.json")
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=365 * cfg.get("lookbackYears", 3))).isoformat()
    today = today.isoformat()
    archived = json.loads((data_dir / "publications.json").read_text())
    added_path = data_dir / "publications-added.json"
    added = json.loads(added_path.read_text())
    existing = archived + added
    titles = {norm(p["title"]) for p in existing}
    dois = {d for p in existing for d in (norm_doi(p.get("doi")), norm_doi(p.get("url"))) if d}
    by_len = [(norm(p["title"]), first_surname(p.get("authors"))) for p in existing]

    def is_known(c):
        t = norm(c["title"])
        if t in titles or norm_doi(c.get("doi")) in dois:
            return True
        fs = first_surname(c.get("authors"))
        return any(abs(len(t) - len(e)) < 20 and fa == fs and difflib.SequenceMatcher(None, t, e).ratio() >= 0.9 for e, fa in by_len)

    s = {"status": None, "since": since, "routes": [], "errors": [], "written": False,
         "policy": "additions are written only when every required route succeeds"}
    works, s["routes"] = openalex_routes(fetch, cfg)
    s["openalexUniqueWorks"] = len(works)
    s["openalexOnlyViaVerifiedIds"] = sum(1 for _, r in works.values() if not any(x.startswith("orcid:") for x in r))
    streams = [("OpenAlex", [openalex_item(w, r, today) for w, r in works.values() if eligible_openalex(w, since)])]
    try:
        streams.append(("Crossref", crossref_items(fetch, cfg, since, today)))
        s["routes"].append({"source": "Crossref", "route": f"orcid:{cfg['orcid']}", "required": True, "ok": True, "fetched": len(streams[-1][1]), "error": None})
    except (SourceError, KeyError, TypeError) as e:
        s["routes"].append({"source": "Crossref", "route": f"orcid:{cfg['orcid']}", "required": True, "ok": False, "fetched": None,
                            "error": str(e) if isinstance(e, SourceError) else f"unexpected response: {e!r}"})
    s["errors"] = [f"{r['source']} {r['route']}: {r['error']}" for r in s["routes"] if not r["ok"]]

    new, skipped = [], {}
    for name, items in streams:
        skipped[name] = 0
        for c in items:
            if is_known(c):
                skipped[name] += 1
                continue
            titles.add(norm(c["title"]))  # make later candidates (and the other source) see earlier additions
            if norm_doi(c.get("doi")): dois.add(norm_doi(c["doi"]))
            by_len.append((norm(c["title"]), first_surname(c.get("authors"))))
            new.append(c)
    s["eligible"] = {name: len(items) for name, items in streams}
    s["skippedExisting"] = skipped
    # Append (never prepend): other data files reference entries by their index ("added:<i>").
    new.sort(key=lambda p: (p.get("date") or str(p.get("year") or 0)))
    listing = [{"key": f"added:{len(added) + i}", "category": p["category"], "year": p.get("year"), "title": p["title"],
                "doi": p.get("doi"), "retrieval": p["retrieval"]} for i, p in enumerate(new)]

    if s["errors"]:
        ok_routes = sum(r["ok"] for r in s["routes"])
        s.update(status="partial" if ok_routes else "failed", added=0, withheld=listing, metadata={"ok": None, "detail": "skipped"})
        return s

    backup = {f: (data_dir / f).read_text() for f in DERIVED if (data_dir / f).exists()}
    try:
        if new:
            added_path.write_text(json.dumps(added + new, indent=1, ensure_ascii=False) + "\n")
        derived(data_dir)  # re-key-sensitive derived data: duplicates and per-person lists
    except Exception as e:
        for f, text in backup.items():
            (data_dir / f).write_text(text)
        s.update(status="failed", added=0, withheld=listing, errors=[f"derived data: {e}"], metadata={"ok": None, "detail": "skipped"})
        return s
    s.update(added=len(new), addedItems=listing, written=True)

    try:
        metrics, pub_meta, detail = metadata(fetch, cfg, works, today)
        (data_dir / "scholar-metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
        (data_dir / "pub-meta.json").write_text(json.dumps(pub_meta, indent=1, ensure_ascii=False) + "\n")
        s.update(status="ok", metadata={"ok": True, "detail": detail})
    except Exception as e:  # optional: never blocks the publication update
        s.update(status="degraded", metadata={"ok": False, "detail": f"metadata refresh failed, files unchanged: {e}"})
    return s


def review_candidates(fetch=get_json, cfg=None):
    """Print same-name OpenAlex author records not yet classified in publication-sources.json, with their recent works.
    Read-only: deciding to trust one is a maintainer's edit to the config."""
    cfg = cfg or load_config()
    known = {a["id"] for k in ("verifiedOpenAlexAuthorIds", "doNotTrust") for a in cfg.get(k, [])}
    orcid_linked = {short_id(a["id"]) for a in fetch("https://api.openalex.org/authors", {"filter": f"orcid:{cfg['orcid']}", "per-page": 25})["results"]}
    found = fetch("https://api.openalex.org/authors", {"search": "Soumik Sarkar", "per-page": 50})["results"]
    for a in found:
        aid = short_id(a["id"])
        if aid in known or aid in orcid_linked:
            continue
        inst = ", ".join(i["display_name"] for i in a.get("last_known_institutions") or [])
        print(f"\n{aid}  {a['display_name']}  orcid={a.get('orcid')}  works={a.get('works_count')}  [{inst}]")
        works = fetch("https://api.openalex.org/works", {"filter": f"authorships.author.id:{aid}", "per-page": 5, "sort": "publication_date:desc",
                                                         "select": "id,title,publication_date,authorships"})["results"]
        for w in works:
            me = [x for x in w["authorships"] if short_id((x.get("author") or {}).get("id")) == aid]
            aff = "; ".join(s for x in me for s in (x.get("raw_affiliation_strings") or []))[:150]
            co = ", ".join(x["author"]["display_name"] for x in w["authorships"][:6])
            print(f"   {short_id(w['id'])} {w.get('publication_date')} {(w.get('title') or '')[:80]}\n      authors: {co}\n      affiliation: {aff}")


def main(argv):
    if "--review-candidates" in argv:
        review_candidates()
        return 0
    s = update()
    if "--summary" in argv:
        Path(argv[argv.index("--summary") + 1]).write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: s[k] for k in ("status", "routes", "openalexUniqueWorks", "skippedExisting", "added", "metadata", "errors") if k in s}))
    for p in s.get("addedItems") or s.get("withheld") or []:
        print(f"{'+' if s['written'] else '(withheld)'} [{p['category']}] {p.get('year')} {p['title'][:100]}  via {', '.join(p['retrieval'])}")
    print(f"status {s['status']}: {s['added']} new publications added" + (f", {len(s['withheld'])} withheld" if s.get("withheld") else ""))
    return 0 if s["status"] in ("ok", "degraded") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
