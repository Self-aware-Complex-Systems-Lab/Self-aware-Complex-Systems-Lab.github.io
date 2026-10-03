"""Attach each person's lab publications (from the de-duplicated publication list) to their profile.

Match = an author in the comma/'and'-separated list equals one of the person's name variants (case/accents/
punctuation-insensitive). Variants: display name, first+last, plus hand aliases for names published differently.
Writes src/data/people-publications.json  {person: [publication keys newest first]} and prints a review table.
"""
import json, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; D = ROOT / "src/data"
people = json.loads((D / "people.json").read_text()); profiles = json.loads((D / "people-profiles.json").read_text())
A = json.loads((D / "publications.json").read_text()); B = json.loads((D / "publications-added.json").read_text())
removed = {r["key"] for r in json.loads((D / "publication-removals.json").read_text())["removals"]}
pubs = [(f"added:{i}", p) for i, p in enumerate(B)] + [(f"archived:{i}", p) for i, p in enumerate(A)]
pubs = [(k, p) for k, p in pubs if k not in removed]

ALIASES = {  # how these names appear in author lists
    "Bernard Lee Xian Yeow": ["Xian Yeow Lee", "Xian Yeow Lee Bernard"],
    "Russell Kai Liang Tan": ["Kai Liang Tan", "Russell Tan"],
    "Sin Yong Tan (Evan)": ["Sin Yong Tan"],
    "Jaydeep-Ravindra Rade": ["Jaydeep Rade", "Jaydeep Ravindra Rade"],
    "Sambit Gadhai": ["Sambit Ghadai"],
    "Fateme Fotouhi Ardakani": ["Fateme Fotouhi"],
    "Muhammad Arbab Arshad": ["Muhammad Arshad", "Arbab Arshad"],
    "Luis G. Riera": ["Luis Riera", "Luis G Riera"],
    "Dr. Soumik Sarkar": [],  # the PI is on every paper; not listed per card
    "Balaji S Sarath Pokuri": ["Balaji Sesha Sarath Pokuri", "Balaji Pokuri", "Balaji SS Pokuri"],
    "Kin Gwn Lore": ["Kin Gwn Lore", "Kin G Lore"],
    "Hsin-Jung Yang": ["Hsin Jung Yang"],
    "Ashutosh Kumar Nirala": ["Ashutosh Nirala"],
    "Seyed Vahid Mirnezami": ["Vahid Mirnezami", "Seyed Vahid Mirnezami"],
    "Adedotun Akintayo": ["Adedotun Akintayo"],
    "Onur Rauf Bingol": ["Onur Bingol", "Onur R Bingol"],
    "Paige K Boor": ["Paige Boor"],
    "Briton R Bauerly": ["Briton Bauerly"],
    "Adrian Kang Wei Chan": ["Adrian Chan"],
    "Zahid Hasan": ["Md Zahid Hasan", "Md. Zahid Hasan"],
    "Truong Tran": ["Troung Tran"],
    "David Leguizamo": ["David Felipe Leguizamo"],
}
def key(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    return re.sub(r"[^a-z]", "", s)
def variants(p):
    name = p["name"].replace("Dr. ", "")
    if p["name"] in ALIASES and ALIASES[p["name"]] == []: return set()
    toks = re.sub(r"\(.*?\)", "", name).split()
    v = {key(name), key(toks[0] + " " + toks[-1])} if len(toks) > 1 else set()
    v |= {key(a) for a in ALIASES.get(p["name"], [])}
    disp = (profiles.get(p["name"]) or {}).get("name")
    if disp: v.add(key(disp))
    return {x for x in v if len(x) > 6}

out = {}
for p in people:
    v = variants(p)
    if not v: continue
    hits = []
    for k, pub in pubs:
        names = [a.strip() for a in re.split(r"\s+and\s+|,\s*", pub.get("authors") or "") if a.strip()]
        # full name, and first + last (ignores middle names / initials such as "Timilehin T. Ayanlade")
        authors = [key(a) for a in names] + [key(a.split()[0] + " " + a.split()[-1]) for a in names if len(a.split()) > 2]
        if v & set(authors): hits.append((pub.get("year") or 0, k))
    if hits: out[p["name"]] = [k for _, k in sorted(hits, reverse=True)]
(D / "people-publications.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(f"{len(out)} of {len(people)} people have lab publications")
for p in people:
    print(f"{len(out.get(p['name'], [])):3d}  {p['name']}")
