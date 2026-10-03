"""Find Sarkar publications newer than / missing from the archived site list.
Sources: OpenAlex (author ORCID 0000-0002-6775-9199, which unites the ISU split profiles)
and the local scrape ~/Desktop/Research/sarkar_papers/_works.json (OpenAlex, 2026-06-22)."""
import json, re, urllib.request, pathlib
ORCID = "0000-0002-6775-9199"
OUT = pathlib.Path("migration/publications-update")
norm = lambda t: re.sub(r"[^a-z0-9]", "", (t or "").lower())
site = json.load(open("src/data/publications.json"))
site_titles = {norm(p["title"]) for p in site}
site_dois = {p["doi"].lower() for p in site if p.get("doi")}

works, cursor = [], "*"
while cursor:
    url = (f"https://api.openalex.org/works?filter=authorships.author.orcid:{ORCID},from_publication_date:2025-01-01"
           f"&per-page=200&cursor={cursor}&mailto=")
    d = json.load(urllib.request.urlopen(url.replace("&mailto=", ""), timeout=60))
    works += d["results"]; cursor = d["meta"].get("next_cursor") if d["results"] else None
json.dump(works, open(OUT / "openalex_raw_2025plus.json", "w"))
local = json.load(open(pathlib.Path.home() / "Desktop/Research/sarkar_papers/_works.json"))

def fmt(w):
    src = (w.get("primary_location") or {}).get("source") or {}
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    return {"title": w["title"], "authors": " and ".join(a["author"]["display_name"] for a in w["authorships"]),
            "venue": src.get("display_name"), "year": w["publication_year"], "date": w.get("publication_date"),
            "type": w.get("type"), "doi": doi, "url": (w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url")),
            "openalex": w["id"], "source": "OpenAlex (fetched 2026-10-03)"}

cands = {}
for w in works:
    if not w.get("title"): continue
    k = norm(w["title"]); doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
    if k in site_titles or (doi and doi in site_dois): continue
    if k not in cands or (w.get("doi") and not cands[k].get("doi")): cands[k] = fmt(w)
for r in local:
    k = norm(r["title"]); doi = (r.get("doi") or "").replace("https://doi.org/", "").lower()
    if k in site_titles or (doi and doi in site_dois) or k in cands: continue
    if (r.get("year") or 0) >= 2025:
        cands[k] = {"title": r["title"], "year": r["year"], "type": r["type"], "doi": doi or None,
                    "url": r.get("doi"), "source": "local scrape sarkar_papers/_works.json (2026-06-22)"}
new = sorted(cands.values(), key=lambda p: (p.get("date") or str(p["year"])), reverse=True)
json.dump(new, open(OUT / "candidates.json", "w"), indent=1, ensure_ascii=False)
print(len(works), "OpenAlex works 2025+;", len(new), "not on archived site")
for p in new: print(p.get("date") or p["year"], "|", p["type"], "|", p["title"][:90], "|", p.get("venue"), "|", p["source"][:20])
