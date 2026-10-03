"""Turn a "📷 Add photos to the website gallery" issue into gallery entries (run by .github/workflows/gallery-upload.yml).

Reads the issue from $GITHUB_EVENT_PATH, downloads every attached image, auto-rotates it, strips all metadata
(including GPS), resizes to at most 2000 px, saves JPEGs under public/assets/gallery/uploads/, and appends entries to
src/data/gallery-uploads.json. Writes a short Markdown summary to $GITHUB_STEP_SUMMARY-like file `gallery-result.md`.
Exit code 2 = nothing usable (no images); 0 = success.
"""
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "public/assets/gallery/uploads"
DATA = ROOT / "src/data/gallery-uploads.json"
MAX_SIDE = 2000


def sections(body: str) -> dict:
    """Issue-form bodies are '### Label\\n\\nvalue' blocks."""
    out, cur = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.*)$", line)
        if m:
            cur = m.group(1).strip().lower(); out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def clean(v):
    return None if not v or v.strip() in ("_No response_", "None") else v.strip()


def slugify(s, n=40):
    return re.sub(r"[^a-z0-9]+", "-", (s or "photo").lower()).strip("-")[:n] or "photo"


def fetch(url, token):
    req = urllib.request.Request(url, headers={"User-Agent": "scslab-gallery-bot", **({"Authorization": f"Bearer {token}"} if token and "github.com" in url else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    issue = event["issue"]
    f = sections(issue.get("body", ""))
    photos_md = f.get("photos", "")
    urls = re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", photos_md) + re.findall(r'<img[^>]+src="(https?://[^"]+)"', photos_md)
    urls += [u for u in re.findall(r"(https://github\.com/user-attachments/assets/[0-9a-f-]+)", photos_md) if u not in urls]
    caption = clean(f.get("caption")) or ""
    date = clean(f.get("date"))
    category = clean(f.get("category")) or "Lab life"
    link = clean(f.get("related link (optional)"))
    credit = clean(f.get("photo credit")) or f"Photo: {issue['user']['login']}"
    token = os.environ.get("GITHUB_TOKEN")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(DATA.read_text()) if DATA.exists() else []
    stamp = dt.date.today().isoformat()
    added, errors = [], []
    for i, u in enumerate(dict.fromkeys(urls), 1):
        try:
            im = Image.open(io.BytesIO(fetch(u, token)))
            im = ImageOps.exif_transpose(im).convert("RGB")   # apply rotation, then drop all metadata
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            name = f"{stamp}-{issue['number']}-{slugify(caption)}-{i}.jpg"
            im.save(OUT_DIR / name, "JPEG", quality=85, optimize=True, progressive=True)
            added.append({"src": f"/assets/gallery/uploads/{name}", "size": list(im.size), "caption": caption, "date": date,
                          "category": category, "link": link, "credit": credit, "issue": issue["number"], "added": stamp,
                          "alt": caption[:140]})
        except Exception as e:
            errors.append(f"{u}: {type(e).__name__}")
    if added:
        DATA.write_text(json.dumps(data + added, indent=1, ensure_ascii=False) + "\n")
    msg = [f"Added **{len(added)}** photo(s) to the gallery." if added else "No photos could be read from this issue."]
    if errors: msg += ["", "Could not read:"] + [f"- {e}" for e in errors]
    Path("gallery-result.md").write_text("\n".join(msg) + "\n")
    print("\n".join(msg))
    sys.exit(0 if added else 2)


if __name__ == "__main__":
    main()
