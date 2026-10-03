"""Apply submissions committed by the token-based form (/contribute-token/) — run by .github/workflows/submissions.yml.

The browser commits one folder per submission:
    submissions/inbox/<id>/submission.json   {"kind": "[Photo]|[News]|…", "title": "...", "fields": {label: value}, "images": {label: [files]}}
    submissions/inbox/<id>/<image files>     (already resized and metadata-free in the browser)

Each submission is converted to the same structure as an issue-form body and handed to the SAME handlers as
contribution_from_issue.py (duplicate detection, alumni moves, news items…). The submitter is the GitHub user who
pushed the commit (GITHUB_ACTOR), which GitHub has already authenticated. Results are written to
submissions/results/<id>.json so the form can show them; the inbox folder is removed.
"""
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contribution_from_issue as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "submissions/inbox"
RESULTS = ROOT / "submissions/results"
HANDLERS = {"[Photo]": C.photo, "[News]": C.news, "[Publication]": C.publication, "[Member]": C.member,
            "[Profile]": C.profile_update, "[Milestone]": C.milestone, "[Grant]": C.grant, "[Award]": C.award}


def main():
    actor = os.environ.get("GITHUB_ACTOR", "unknown")
    RESULTS.mkdir(parents=True, exist_ok=True)
    done = 0
    for folder in sorted(p for p in INBOX.glob("*") if p.is_dir()):
        sub_id = folder.name
        try:
            s = json.loads((folder / "submission.json").read_text())
            fields = {k.lower(): (v or "").strip() for k, v in s.get("fields", {}).items()}
            # image fields become markdown pointing at the committed files (file:// URLs are read by C.save_image)
            for label, files in (s.get("images") or {}).items():
                fields[label.lower()] = "\n".join(f"![{Path(f).name}]({(folder / Path(f).name).resolve().as_uri()})" for f in files)
            issue = {"number": int(sub_id.split("-")[0]) if sub_id.split("-")[0].isdigit() else 0,
                     "title": f"{s['kind']} {s.get('title', '')}", "user": {"login": actor}}
            handler = HANDLERS.get(s["kind"])
            code, msg = handler(issue, fields, None) if handler else (2, f"Unknown submission type {s.get('kind')!r}.")
        except Exception as e:  # never leave a broken submission blocking the inbox
            code, msg = 2, f"Could not process this submission: {type(e).__name__}: {e}"
        (RESULTS / f"{sub_id}.json").write_text(json.dumps({"id": sub_id, "ok": code == 0, "code": code, "message": msg, "by": actor}, indent=1) + "\n")
        shutil.rmtree(folder)
        print(f"{sub_id}: {msg}")
        done += 1
    print(f"{done} submission(s) processed")


if __name__ == "__main__":
    main()
