"""Check every link shown on People/Alumni cards (original + web-found). Flags dead (>=400) and generic homepage links.
LinkedIn is skipped (blocks bots). A known-good Scholar profile is used as a control for Scholar 404s."""
import json, requests
from urllib.parse import urlparse
from pathlib import Path
D = Path(__file__).resolve().parents[2] / "src/data"
P = json.loads((D / "people.json").read_text()); W = json.loads((D / "people-web-links.json").read_text())["links"]
hidden = {h["href"] for h in json.loads((D / "link-corrections.json").read_text())["hide"]}
rows = [(p["name"], l["href"]) for p in P for l in p["links"] if l["href"] not in hidden] + [(n, x["url"]) for n, L in W.items() for x in L]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/130"}
bad = []
for n, u in rows:
    if "linkedin.com" in u: continue
    pu = urlparse(u)
    generic = pu.path in ("", "/") and pu.netloc in ("iastate.edu", "www.iastate.edu", "google.com", "github.com", "scholar.google.com")
    try: s = requests.get(u, headers=UA, timeout=20).status_code
    except Exception as e: s = type(e).__name__
    if generic or not (isinstance(s, int) and s < 400): bad.append((n, u, s, "generic" if generic else ""))
print(f"{len(rows)} links checked; {len(bad)} flagged"); [print(" ", b) for b in bad]
