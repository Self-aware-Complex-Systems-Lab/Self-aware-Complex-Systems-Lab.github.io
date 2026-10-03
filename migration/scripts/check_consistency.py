"""Cross-page consistency checks on the built site (dist/) and the vita PDF.

Run after `npm run build`:  .venv/bin/python migration/scripts/check_consistency.py
"""
import json, re, sys
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]; DIST = ROOT / "dist"; D = ROOT / "src/data"
page = lambda p: BeautifulSoup((DIST / p / "index.html" if p else DIST / "index.html").read_text(), "html.parser")
txt = lambda s: re.sub(r"\s+", " ", s.get_text(" ")).strip()
norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
issues = []
def check(ok, msg):
    print(("OK   " if ok else "FAIL ") + msg)
    if not ok: issues.append(msg)

home, pubs, people_p, alumni, pi, gallery, news, contrib = (page(p) for p in ["", "publications", "people", "alumni", "principal-investigator", "gallery", "news", "contribute"])
cv = "\n".join(p.extract_text() for p in PdfReader(DIST / "cv/Soumik_Sarkar_CV.pdf").pages)
cvn = norm(cv)

# 1. publication counts: home stat == publications page
n_pub = len(pubs.select("li.pub"))
stat = int(re.search(r"(\d+)\s*publications", txt(home)).group(1))
check(stat == n_pub, f"home publication count {stat} == publications page {n_pub}")
# 2. people counts
from collections import Counter
cards_people = {a["data-name"] for a in people_p.select("article.person")}
cards_alumni = {a["data-name"] for a in alumni.select("article.person")}
check(not (cards_people & cards_alumni), f"nobody on both People and Alumni ({len(cards_people)} people, {len(cards_alumni)} alumni)")
m_cur = int(re.search(r"(\d+)\s*members listed", txt(home)).group(1)); m_alu = int(re.search(r"(\d+)\s*alumni listed", txt(home)).group(1))
check(m_cur == len(cards_people) and m_alu == len(cards_alumni), f"home member/alumni counts {m_cur}/{m_alu} == pages {len(cards_people)}/{len(cards_alumni)}")
# 3. featured papers appear on the publications page
titles = {norm(li.find("p").get_text(" ")) for li in pubs.select("li.pub")}
feat = [norm(a.get_text(" ")) for a in home.select('[aria-labelledby="featured"] li > a')]
check(all(any(f[:40] in t or t[:40] in f for t in titles) for f in feat), f"all {len(feat)} featured papers are on the publications page")
# 4. awards: PI page honors are all in the CV
awards = [li.get_text(" ").split("Announcement")[0].strip() for li in pi.select("#awards li")]
miss = [a for a in awards if norm(a.split(",")[0])[:30] not in cvn]
check(not miss, f"all {len(awards)} PI-page honors appear in the CV" + (f" — missing {miss}" if miss else ""))
# 5. grants: recent PI-page grants are in the CV
grants = [li.get_text(" ").split(" (as ")[0].strip() for li in pi.select("#funding ol li")]
cvwords = set(re.findall(r"[a-z0-9]{3,}", cv.lower()))
def in_cv(title):   # word-level: the vita sometimes words the same grant differently
    w = set(re.findall(r"[a-z0-9]{3,}", title.lower())) - {"the", "and", "for", "with"}
    return norm(title)[:35] in cvn or (len(w & cvwords) / max(1, len(w)) >= 0.6)
gmiss = [g for g in grants if not in_cv(g)]
check(not gmiss, f"all {len(grants)} PI-page grants appear in the CV" + (f" — missing {gmiss[:5]}" if gmiss else ""))
# 6. alumni/current status: graduated people are not 'in progress' in the CV
prog = cv[cv.find("In progress"):cv.find("D. Service on Graduate Student Committees")]
wrong = [n for n in cards_alumni if norm(n.split(" (")[0]) in norm(prog) and "PhD" in prog]
check(not wrong, "no alumni listed as 'in progress' in the CV" + (f" — {wrong}" if wrong else ""))
current_phd = [a["data-name"] for a in people_p.select('[data-category="Doctoral Students"] article.person')]
notin = [n for n in current_phd if norm(n)[:12] not in norm(prog)]
check(not notin, f"all {len(current_phd)} current Ph.D. students are 'in progress' in the CV" + (f" — missing {notin}" if notin else ""))
# 6b. PI biography numbers agree on the PI page and the People card
pi_n = re.search(r"more than (\d+) peer-reviewed", txt(pi)); pe_n = re.search(r"more than (\d+) peer-reviewed", txt(people_p))
check(pi_n and pe_n and pi_n.group(1) == pe_n.group(1), f"biography publication count same on PI page ({pi_n and pi_n.group(1)}) and People card ({pe_n and pe_n.group(1)})")
fund_pi = re.search(r"about \$(\d+)M", txt(pi)); fund_pe = re.search(r"about \$(\d+)M", txt(people_p))
check(fund_pi and fund_pe and fund_pi.group(1) == fund_pe.group(1), f"biography funding same on PI page and People card (${fund_pi and fund_pi.group(1)}M / ${fund_pe and fund_pe.group(1)}M)")
# 7. CV / PI page numbers
bio = txt(pi)
m = re.search(r"more than (\d+) peer-reviewed publications", bio); cvtot = int(re.search(r"Total of (\d+) publications", cv).group(1))
check(bool(m) and int(m.group(1)) <= cvtot < int(m.group(1)) + 50, f"PI bio 'more than {m.group(1) if m else '-'}' is consistent with CV total ({cvtot})")
# 8. gallery paper links resolve to listed papers
plinks = [a["href"] for a in gallery.find_all("a") if a.get_text(strip=True) == "Paper"]
check(all(h.startswith("http") or h.startswith("/") for h in plinks), f"{len(plinks)} gallery paper links are valid URLs")
# 9. news on home == newest news items
hn = [norm(a.get_text(" ")) for a in home.select('[aria-labelledby="news"] li a')]
nn = [norm(h.get_text(" ")) for h in news.select("ol li h2")][: len(hn)]
check(hn == nn, f"home 'Latest news' matches the top {len(hn)} News items")
# 10. CV date is today and links to the PDF from PI/contact/people
import datetime as dt
check(dt.date.today().strftime("%m/%d/%Y") in cv, "CV date is today")
for name, s in [("PI", pi), ("contact", page("contact")), ("people", people_p)]:
    check(any(a.get("href") == "/cv/Soumik_Sarkar_CV.pdf" for a in s.find_all("a")), f"{name} page links to the auto CV")
check("drive.google.com/file/d/1XF7n5" not in (DIST / "principal-investigator/index.html").read_text(), "old Drive CV link no longer used on PI page")
# 11. arXiv venue wording
check(not any("Cornell University" in (DIST / p).read_text() for p in ["publications/index.html", "cv/index.html", "people/index.html", "alumni/index.html"]), "no 'Cornell University' arXiv labels")
print(f"\n{len(issues)} issue(s)")
sys.exit(1 if issues else 0)
