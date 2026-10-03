"""Parse the publications embed (archived verbatim at migration/archive/publications/embed.html)."""
import json, re
from bs4 import BeautifulSoup
s = BeautifulSoup(open("migration/archive/publications/embed.html").read(), "html.parser")
tabs = {b["onclick"].split("'")[1]: b.get_text(strip=True) for b in s.select("button.tab")}
pubs = []
for tab in s.select("div.tab-content"):
    for it in tab.select("div.publication-item"):
        g = lambda c: (it.select_one("." + c).get_text(" ", strip=True) if it.select_one("." + c) else None)
        venue = g("pub-venue"); m = re.search(r"\((\d{4})\)\s*$", venue or "")
        link = it.select_one("a.pub-link"); href = link["href"] if link else None
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", href) if href and "doi.org/" in href else None
        pubs.append({"category": tab["id"], "categoryLabel": tabs.get(tab["id"]), "number": g("pub-number"),
                     "title": g("pub-title"), "authors": g("pub-authors"), "venue": venue,
                     "year": int(m.group(1)) if m else None, "citationsAsOfArchive": g("citation-badge"),
                     "url": href, "doi": doi, "source": "https://sites.google.com/view/scslab-isu/publications"})
json.dump(pubs, open("src/data/publications.json", "w"), indent=1, ensure_ascii=False)
from collections import Counter
print(len(pubs), Counter(p["category"] for p in pubs), sum(1 for p in pubs if not p["year"]), sum(1 for p in pubs if not p["url"]))
print(len(s.select("div.publication-item")))
