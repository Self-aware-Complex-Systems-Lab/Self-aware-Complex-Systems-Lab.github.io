"""Derive small site data files from image-manifest.json (single source of truth for assets)."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; m = json.loads((ROOT / "migration/image-manifest.json").read_text())
E = m["entries"]
first = lambda pred: [e for e in E if pred(e) and not e.get("duplicateOfFirstOccurrence")]
research = {e["associatedName"] or "Research Areas": {"src": "/assets/" + e["localPath"], "manifestId": e["id"], "size": e["downloadedDimensions"]}
            for e in E if e["group"] == "research"}
sponsors = [{"name": e["associatedName"], "src": "/assets/" + e["localPath"], "manifestId": e["id"], "size": e["downloadedDimensions"]}
            for e in sorted([e for e in E if e["group"] == "sponsors"], key=lambda e: e["occurrenceIndex"])]
gallery = [{"caption": e["associatedName"], "src": "/assets/" + e["localPath"], "manifestId": e["id"], "size": e["downloadedDimensions"],
            "originalPage": e["originalPageUrl"]} for e in sorted([e for e in E if e["group"] == "gallery"], key=lambda e: e["occurrenceIndex"])]
pi = [{"src": "/assets/" + e["localPath"], "manifestId": e["id"], "page": e["originalPageUrl"]} for e in E if e["group"] == "pi"]
logo = next("/assets/" + e["localPath"] for e in E if e["group"] == "site")
out = {"research": research, "sponsors": sponsors, "gallery": gallery, "pi": pi, "logo": logo}
(ROOT / "src/data/assets.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(research), len(sponsors), len(gallery), pi, logo)
