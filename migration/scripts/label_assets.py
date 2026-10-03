"""Attach human-verified labels to images that have no alt text / name in the DOM
(sponsor logos, group photos). Keyed by SHA-256 prefix so it is stable across re-runs.
Labels were assigned by visually inspecting each image (contact sheet), not by position."""
import json
from pathlib import Path
LABELS = {
 "0ae3396b09": ("sponsors", "arpa-e", "ARPA-E"), "49e104a361": ("sponsors", "nsf", "National Science Foundation (NSF)"),
 "505a417bcd": ("sponsors", "usda-nifa", "USDA-NIFA"), "5127f7ce65": ("sponsors", "fhwa", "U.S. DOT Federal Highway Administration"),
 "5707db25b8": ("sponsors", "nvidia", "NVIDIA"), "575e44992a": ("sponsors", "rockwell-collins", "Rockwell Collins"),
 "69eeef9648": ("sponsors", "iowa-state-university", "Iowa State University"), "6fc646fbf2": ("sponsors", "ansys", "ANSYS"),
 "7b30537e12": ("sponsors", "nih", "National Institutes of Health (NIH)"), "93f781b22f": ("sponsors", "toyota", "Toyota"),
 "d19fc140a1": ("sponsors", "afosr", "Air Force Office of Scientific Research (AFOSR)"), "db1b9e440a": ("sponsors", "darpa", "DARPA"),
 "de4206d61a": ("sponsors", "iowa-energy-center", "Iowa Energy Center"),
 "60ce8762ec": ("gallery", "lab-group-photo-storefront", "Lab group photo (home page header image)"),
 "56e7ff61a6": ("gallery", "lab-group-photo-outdoor-sculpture", "Lab group photo outdoors (home page section background)"),
 "ae8cb8efa8": ("gallery", "lab-celebration", "Lab members celebrating with a cake (home page section background)"),
 "e3f498552d": ("gallery", "lab-group-photo-indoor", "Lab group photo indoors (home page section background)"),
}
ROOT = Path(__file__).resolve().parents[2]; PUB = ROOT / "public/assets"
mp = ROOT / "migration/image-manifest.json"; m = json.loads(mp.read_text())
for e in m["entries"]:
    lab = LABELS.get((e.get("sha256") or "")[:10])
    if not lab: continue
    g, stem, label = lab; ext = e["localPath"].rsplit(".", 1)[1]; new = f"{g}/{stem}.{ext}"
    old = PUB / e["localPath"]
    if old.exists() and not (PUB / new).exists(): old.rename(PUB / new)
    e.update(localPath=new, localFile="public/assets/" + new, localFilename=new.rsplit("/", 1)[1],
             associatedName=label, labelSource="visual inspection of image content (no alt text / caption in original DOM)")
mp.write_text(json.dumps(m, indent=1, ensure_ascii=False)); print("labelled")
