"""Extract funding/grant records from the archived TrAC pages -> funding-sarkar.json.

Sources: the two structured grant listings (federal-funded + seed-fund cards).
All values are copied verbatim from the rendered HTML; fields the site does not
show are null. Grants that do not name Soumik Sarkar are included with
role=null and mentionsSarkar=false, because the site shows only one PI (federal)
or Awardee/Co-PIs (seed) and gives no full personnel list.
"""
import json, re
from pathlib import Path
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
BASE = "https://trac-ai.iastate.edu"
SARKAR = re.compile(r"\b(S\.?\s+Sarkar|Soumik\s+Sarkar)\b")
FED = ("research__projects__federal-funded-projects", f"{BASE}/research/projects/federal-funded-projects/")
SEED = ("research__projects__seed-fund-projects", f"{BASE}/research/projects/seed-fund-projects/")

def fields(card):
    out = {}
    for s in card.find_all("strong"):
        k = s.get_text(strip=True).rstrip(":")
        v = s.parent.get_text(" ", strip=True)[len(s.get_text(strip=True)):].strip()
        out[k] = v
    return out

def split_names(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else []

def role_of(pi, copis):
    if any(SARKAR.fullmatch(p) or SARKAR.search(p) for p in pi): return "PI"
    if any(SARKAR.search(p) for p in copis): return "Co-PI"
    return None

def term_dates(term):
    if not term: return None, None
    parts = re.split(r"\s+[–-]\s+", term)
    return (parts[0], parts[1]) if len(parts) == 2 else (term, None)

recs = []
soup = BeautifulSoup((HERE / "pages" / FED[0] / "rendered.html").read_text(), "html.parser")
for strong in soup.find_all("strong", string=re.compile(r"^PI:")):
    card = strong.find_parent("div").find_parent("div").find_parent("div").find_parent("div")
    title = card.find("div", style=re.compile("font-weight:700")).get_text(" ", strip=True)
    f = fields(card)
    a = card.find("a", string=re.compile("More Information"))
    pi = split_names(f.get("PI"))
    start, end = term_dates(f.get("Term"))
    # thrust group heading preceding the card (e.g. "Food, Energy, Water")
    recs.append({"title": re.sub(r"\s+", " ", title), "listing": "Federal Funded Projects", "sponsor": f.get("Funding Agency"),
        "program": None, "researchThrust": f.get("Research Thrust"), "role": role_of(pi, []),
        "pi": f.get("PI"), "coPIs": None, "otherPIs": [p for p in pi if not SARKAR.search(p)],
        "amount": f.get("Award"), "term": f.get("Term"), "start": start, "end": end, "status": None, "year": None,
        "awardNumber": None, "descriptionExcerpt": None, "moreInfoUrl": a["href"] if a else None,
        "sourceUrl": FED[1]})
soup = BeautifulSoup((HERE / "pages" / SEED[0] / "rendered.html").read_text(), "html.parser")
for card in soup.select(".seedgrant-card"):
    f = fields(card)
    pi, co = split_names(f.get("Awardees")), split_names(f.get("Co-PIs"))
    role = role_of(pi, co)
    recs.append({"title": re.sub(r"\s+", " ", card.select_one(".seedgrant-card-title").get_text(" ", strip=True)), "listing": "Seed Fund Projects",
        "sponsor": "Translational AI Center (TrAC), Iowa State University", "program": "TrAC Seed Grant Program",
        "researchThrust": None, "role": role, "pi": f.get("Awardees"), "coPIs": f.get("Co-PIs"),
        "otherPIs": [p for p in pi + co if not SARKAR.search(p)], "amount": f.get("Award"), "term": None,
        "start": None, "end": None, "status": f.get("Status"), "year": f.get("Year"), "awardNumber": None,
        "descriptionExcerpt": None, "moreInfoUrl": None, "sourceUrl": SEED[1]})
for r in recs:
    r["mentionsSarkar"] = r["role"] is not None
    if r["listing"] == "Seed Fund Projects":
        r["sponsorNote"] = "sponsor inferred from page context ('The TrAC Seed Grant Program'); not printed on the card"
recs.sort(key=lambda r: (not r["mentionsSarkar"], r["listing"], r["title"]))
(HERE / "funding-sarkar.json").write_text(json.dumps(recs, indent=1, ensure_ascii=False))
n = sum(r["mentionsSarkar"] for r in recs)
print(f"{len(recs)} grants; {n} name Sarkar ({sum(r['role']=='PI' for r in recs)} PI, {sum(r['role']=='Co-PI' for r in recs)} Co-PI)")
