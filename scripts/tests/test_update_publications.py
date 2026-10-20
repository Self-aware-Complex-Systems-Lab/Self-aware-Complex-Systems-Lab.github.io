"""Offline regression tests for scripts/update_publications.py (no network; the APIs are faked).

    python -m unittest discover -s scripts/tests -v
"""
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_publications as up  # noqa: E402

TODAY = dt.date(2026, 10, 19)
PI = "0000-0002-6775-9199"
VERIFIED = "A5158521094"
UNVERIFIED = "A5153546885"


ISU = {"id": "https://openalex.org/I173911158", "display_name": "Iowa State University"}
ELSEWHERE = {"id": "https://openalex.org/I1", "display_name": "VIT-AP University"}


def work(wid, title, author_ids, doi=None, date="2026-10-09", wtype="preprint", source_type="repository"):
    return {"id": f"https://openalex.org/{wid}", "title": title, "doi": f"https://doi.org/{doi}" if doi else None,
            "type": wtype, "publication_year": int(date[:4]), "publication_date": date,
            "primary_location": {"source": {"type": source_type, "display_name": "arXiv (Cornell University)"},
                                 "landing_page_url": f"https://example.org/{wid}"},
            "authorships": [{"author": {"id": f"https://openalex.org/{a}", "display_name": n}, "raw_author_name": n,
                             "institutions": [ISU if isu else ELSEWHERE]} for a, n, *flag in author_ids for isu in [flag[0] if flag else True]],
            "corresponding_author_ids": []}


TARGET = work("W7221554556", "Personalized Federated Direct Preference Optimization via LoRA Adapters",
              [("A5158496004", "Zhanhong Jiang"), (VERIFIED, "Soumik Sarkar")], doi="10.48550/arxiv.2610.12885")
ORCID_WORK = work("W1", "A Paper Found Through The ORCID Route", [("A5081037761", "Soumik Sarkar")], doi="10.1000/orcid.1", date="2026-05-01")
SAME_NAME = work("W9", "Spacecraft Trajectory Paper From An Unreviewed Same Name Record", [(UNVERIFIED, "Soumik Sarkar")], date="2026-06-19")


class FakeAPI:
    """Answers OpenAlex/Crossref queries from in-memory works, page by page, and records every call."""

    def __init__(self, orcid_works=(), by_author=None, crossref=(), per_page=None, fail=(), authors_fail=False, isu_name_hits=()):
        self.orcid_works, self.by_author, self.crossref = list(orcid_works), by_author or {}, list(crossref)
        self.isu_name_hits = list(isu_name_hits)
        self.per_page, self.fail, self.authors_fail, self.calls = per_page, set(fail), authors_fail, []

    def __call__(self, base, params):
        self.calls.append((base, dict(params)))
        if base.endswith("/authors"):
            if self.authors_fail:
                raise up.SourceError("HTTP 503 from authors")
            return {"results": [{"id": "https://openalex.org/A5081037761", "works_count": 358, "cited_by_count": 1,
                                 "summary_stats": {"h_index": 1, "i10_index": 1}}]}
        if "crossref" in base:
            if "crossref" in self.fail:
                raise up.SourceError("HTTP 503 from crossref")
            return {"message": {"items": self.crossref if params["cursor"] == "*" else [], "next-cursor": "c2"}}
        filt = params["filter"]
        if filt.startswith("authorships.author.orcid:"):
            if "orcid" in self.fail:
                raise up.SourceError("HTTP 429 from openalex")
            rows = self.orcid_works
        elif filt.startswith("raw_author_name.search:"):
            if "auto" in self.fail:
                raise up.SourceError("HTTP 503 from openalex")
            rows = self.isu_name_hits
        else:
            if "author" in self.fail:
                raise up.SourceError("HTTP 500 from openalex")
            ids = filt.split(":", 1)[1].split("|")
            rows = [w for i in ids for w in self.by_author.get(i, [])]
        per = self.per_page or params["per-page"]
        page = params["page"]
        return {"meta": {"count": len(rows)}, "results": rows[(page - 1) * per: page * per]}


def config(verified=(VERIFIED,)):
    return {"name": "Soumik Sarkar", "orcid": PI, "lookbackYears": 3,
            "verifiedOpenAlexAuthorIds": [{"id": i, "evidence": ["https://openalex.org/W7221554556"]} for i in verified]}


def history(n=3):
    """ORCID-linked works co-authored with Zhanhong Jiang, so he counts as a recurring co-author (MIN_SHARED)."""
    return [work(f"WH{i}", f"Older paper {chr(65 + i)} on distributed {['learning', 'control', 'sensing', 'fusion'][i]}",
                 [("A5000000001", "Zhanhong Jiang"), ("A5081037761", "Soumik Sarkar")], doi=f"10.1000/h{i}", date="2015-01-01") for i in range(n)]


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.archived = [{"category": "journals", "title": "An Archived Journal Paper", "authors": "Soumik Sarkar", "year": 2020,
                          "doi": "10.1000/ARCHIVED.7"}]
        self.added = [{"category": "conferences", "title": "First Added Paper", "authors": "A. Person and Soumik Sarkar", "year": 2025},
                      {"category": "preprints", "title": "Second Added Paper", "authors": "B. Person", "year": 2025,
                       "url": "https://doi.org/10.1000/Added.2"}]
        self.write("publications.json", self.archived)
        self.write("publications-added.json", self.added)
        self.write("scholar-metrics.json", {"old": True})
        self.write("pub-meta.json", {"old": True})

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, obj):
        (self.d / name).write_text(json.dumps(obj, indent=1) + "\n")

    def read(self, name):
        return json.loads((self.d / name).read_text())

    def run_update(self, api, cfg=None):
        return up.update(data_dir=self.d, cfg=cfg or config(), fetch=api, today=TODAY, derived=lambda d: None)

    def added_titles(self):
        return [p["title"] for p in self.read("publications-added.json")]

    def test_verified_author_id_supplies_work_missing_from_orcid_route(self):
        s = self.run_update(FakeAPI(orcid_works=[ORCID_WORK], by_author={VERIFIED: [TARGET]}))
        self.assertEqual(s["status"], "ok")
        new = self.read("publications-added.json")[2:]
        target = next(p for p in new if p["openalex"].endswith("W7221554556"))
        self.assertEqual(target["retrieval"], [f"openalex-author:{VERIFIED}"])
        self.assertEqual((target["category"], target["venue"], target["year"]), ("preprints", "arXiv", 2026))
        self.assertEqual(target["authors"], "Zhanhong Jiang and Soumik Sarkar")
        self.assertEqual(target["url"], "https://doi.org/10.48550/arxiv.2610.12885")

    def test_auto_match_imports_paper_on_unknown_record_without_any_config(self):
        s = self.run_update(FakeAPI(orcid_works=history(), isu_name_hits=[TARGET]), cfg=config(verified=()))
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["addedItems"][0]["title"], TARGET["title"])
        self.assertTrue(s["addedItems"][0]["retrieval"][0].startswith(f"auto-match:{VERIFIED} (Iowa State; co-authors Zhanhong Jiang"))

    def test_auto_match_rejects_without_per_paper_evidence(self):
        no_isu = work("W10", "Neoliberalism and economic discourse", [("A5101953320", "Soumik Sarkar", False), ("A7", "Zhanhong Jiang")])
        no_coauthor = work("W11", "Light-active antibiotics", [("A5101872766", "Soumik Sarkar"), ("A8", "Supriya Bhunia")])
        other_name = work("W12", "Retail customer journeys", [("A5133472864", "S K Nasrin Sultana Raj Sarkar"), ("A7", "Zhanhong Jiang")])
        excluded = work("W13", "Excluded record paper", [("A5999", "Soumik Sarkar"), ("A7", "Zhanhong Jiang")])
        cfg = dict(config(verified=()), excludeAuthorIds=[{"id": "A5999"}])
        s = self.run_update(FakeAPI(orcid_works=history(), isu_name_hits=[no_isu, no_coauthor, other_name, excluded]), cfg=cfg)
        self.assertEqual(s["added"], 0)
        reasons = {r["openalex"].rsplit("/", 1)[-1]: r["reason"] for r in s["routes"][1]["rejected"]}
        self.assertEqual(set(reasons), {"W10", "W11", "W12", "W13"})
        self.assertIn("co-author", reasons["W11"])

    def test_auto_match_uses_paper_name_not_mixed_record_name(self):
        mixed = work("W14", "Spacecraft trajectory correctors", [("A5000000001", "Zhanhong Jiang"), ("A5133472864", "S K Nasrin Sultana Raj Sarkar")])
        mixed["authorships"][1]["raw_author_name"] = "Soumik Sarkar"
        s = self.run_update(FakeAPI(orcid_works=history(), isu_name_hits=[mixed]), cfg=config(verified=()))
        self.assertEqual(s["added"], 1)
        self.assertEqual(self.read("publications-added.json")[-1]["authors"], "Zhanhong Jiang and Soumik Sarkar")

    def test_auto_match_failure_is_a_route_failure(self):
        s = self.run_update(FakeAPI(orcid_works=history(), isu_name_hits=[TARGET], fail={"auto"}), cfg=config(verified=()))
        self.assertEqual((s["status"], s["written"]), ("partial", False))

    def test_work_returned_by_both_routes_is_added_once(self):
        both = work("W7221554556", TARGET["title"], [(VERIFIED, "Soumik Sarkar"), ("A5081037761", "Soumik Sarkar")], doi="10.48550/arxiv.2610.12885")
        s = self.run_update(FakeAPI(orcid_works=[both], by_author={VERIFIED: [both]}))
        self.assertEqual(s["openalexUniqueWorks"], 1)
        self.assertEqual(self.added_titles().count(TARGET["title"]), 1)
        self.assertEqual(s["addedItems"][0]["retrieval"], [f"orcid:{PI}", f"openalex-author:{VERIFIED}"])

    def test_unverified_same_name_author_is_not_queried_or_imported(self):
        api = FakeAPI(orcid_works=[ORCID_WORK], by_author={VERIFIED: [TARGET], UNVERIFIED: [SAME_NAME]})
        self.run_update(api)
        self.assertNotIn(SAME_NAME["title"], self.added_titles())
        self.assertFalse(any(UNVERIFIED in p.get("filter", "") for _, p in api.calls))

    def test_openalex_pages_are_followed_to_the_end(self):
        topics = ["Soybean canopy imaging", "Federated optimization", "Topology design", "Insect pest detection", "Wastewater control"]
        works = [work(f"W{i}", t, [("A5081037761", "Soumik Sarkar")], doi=f"10.1000/p{i}", date="2026-01-01") for i, t in enumerate(topics)]
        api = FakeAPI(orcid_works=works, per_page=2)
        s = self.run_update(api, cfg=config(verified=()))
        self.assertEqual([p["page"] for b, p in api.calls if p.get("filter", "").startswith("authorships.author.orcid:")], [1, 2, 3])
        self.assertEqual(s["added"], 5)

    def test_short_page_set_is_a_failure_not_success(self):
        api = FakeAPI(orcid_works=[ORCID_WORK])
        real = api.__call__
        api_call = lambda b, p: dict(real(b, p), meta={"count": 3}) if b.endswith("/works") else real(b, p)
        s = up.update(data_dir=self.d, cfg=config(verified=()), fetch=api_call, today=TODAY, derived=lambda d: None)
        self.assertEqual(s["status"], "partial")
        self.assertIn("1 distinct works but reported 3", s["errors"][0])

    def test_opaque_cursor_is_percent_encoded_and_round_trips(self):
        cursor = "AoJ+k/8=x&y"
        urls = []

        def opener(req, timeout):
            urls.append(req.full_url)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            items = [{"title": ["Crossref Paper"], "type": "journal-article", "DOI": "10.1000/cr", "author": []}] if q["cursor"] == ["*"] else []
            return io.BytesIO(json.dumps({"message": {"items": items, "next-cursor": cursor}}).encode())

        fetch = lambda b, p: up.get_json(b, p, opener=opener, sleep=lambda s: None)
        items = up.crossref_items(fetch, config(), "2023-10-20", "2026-10-19")
        self.assertEqual(len(items), 1)
        self.assertNotIn("+", urls[1].split("cursor=")[1].split("&")[0])
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(urls[1]).query)["cursor"], [cursor])

    def test_doi_variants_match_existing_entries(self):
        self.assertEqual(up.norm_doi("https://dx.doi.org/10.1000/ABC"), "10.1000/abc")
        self.assertEqual(up.norm_doi("doi:10.1000/abc"), "10.1000/abc")
        renamed = [work("W2", "Different Title For The Archived Paper", [("A5081037761", "Soumik Sarkar")], doi="10.1000/archived.7", date="2026-02-01"),
                   work("W3", "Another Title For The Added Preprint", [("A5081037761", "Soumik Sarkar")], doi="10.1000/ADDED.2", date="2026-02-01")]
        s = self.run_update(FakeAPI(orcid_works=renamed), cfg=config(verified=()))
        self.assertEqual(s["added"], 0)
        self.assertEqual(s["skippedExisting"]["OpenAlex"], 2)

    def test_existing_target_is_not_appended_again(self):
        self.write("publications-added.json", self.added + [{"category": "preprints", "title": TARGET["title"], "authors": "Zhanhong Jiang and Soumik Sarkar",
                                                            "year": 2026, "doi": "10.48550/ARXIV.2610.12885"}])
        s = self.run_update(FakeAPI(by_author={VERIFIED: [TARGET]}))
        self.assertEqual(s["added"], 0)
        self.assertEqual(self.added_titles().count(TARGET["title"]), 1)

    def test_existing_order_and_positional_keys_are_stable(self):
        before = (self.d / "publications.json").read_text()
        self.run_update(FakeAPI(orcid_works=[ORCID_WORK], by_author={VERIFIED: [TARGET]}))
        after = self.read("publications-added.json")
        self.assertEqual(after[:2], self.added)  # added:0 and added:1 unchanged
        self.assertEqual((self.d / "publications.json").read_text(), before)
        self.assertEqual([p["title"] for p in after[2:]], [ORCID_WORK["title"], TARGET["title"]])  # appended, by date

    def test_source_failure_differs_from_successful_empty_response(self):
        before = {f: (self.d / f).read_text() for f in ("publications-added.json", "scholar-metrics.json", "pub-meta.json")}
        failed = self.run_update(FakeAPI(by_author={VERIFIED: [TARGET]}, fail={"orcid"}))
        self.assertEqual((failed["status"], failed["written"], failed["added"]), ("partial", False, 0))
        self.assertEqual([p["title"] for p in failed["withheld"]], [TARGET["title"]])
        self.assertIn("HTTP 429", failed["errors"][0])
        self.assertEqual({f: (self.d / f).read_text() for f in before}, before)  # nothing written, nothing removed
        everything = self.run_update(FakeAPI(fail={"orcid", "author", "auto", "crossref"}))
        self.assertEqual(everything["status"], "failed")
        empty = self.run_update(FakeAPI())
        self.assertEqual((empty["status"], empty["added"], empty["errors"]), ("ok", 0, []))

    def test_metadata_failure_is_degraded_and_leaves_metadata_files(self):
        s = self.run_update(FakeAPI(by_author={VERIFIED: [TARGET]}, authors_fail=True))
        self.assertEqual((s["status"], s["added"], s["metadata"]["ok"]), ("degraded", 1, False))
        self.assertEqual(self.read("scholar-metrics.json"), {"old": True})
        self.assertEqual(self.read("pub-meta.json"), {"old": True})

    def test_corresponding_authors_cover_verified_id_works(self):
        corr = dict(TARGET, corresponding_author_ids=[f"https://openalex.org/{VERIFIED}"])
        self.run_update(FakeAPI(by_author={VERIFIED: [corr]}))
        self.assertEqual(list(self.read("pub-meta.json")["byTitle"].values())[0]["corresponding"], ["Soumik Sarkar"])

    def test_second_run_with_same_data_adds_nothing(self):
        api = lambda: FakeAPI(orcid_works=[ORCID_WORK], by_author={VERIFIED: [TARGET]})
        self.assertEqual(self.run_update(api())["added"], 2)
        snapshot = (self.d / "publications-added.json").read_text()
        second = self.run_update(api())
        self.assertEqual((second["status"], second["added"]), ("ok", 0))
        self.assertEqual((self.d / "publications-added.json").read_text(), snapshot)


class RetryTest(unittest.TestCase):
    def opener(self, codes, headers=None):
        calls = []

        def op(req, timeout):
            calls.append(req.full_url)
            code = codes[min(len(calls), len(codes)) - 1]
            if code == "timeout":
                raise urllib.error.URLError("timed out")
            if code != 200:
                raise urllib.error.HTTPError(req.full_url, code, "err", headers or {}, None)
            return io.BytesIO(b'{"ok": true}')
        return op, calls

    def test_transient_errors_are_retried_a_bounded_number_of_times(self):
        op, calls = self.opener([503])
        sleeps = []
        with self.assertRaises(up.SourceError) as e:
            up.get_json("https://api.openalex.org/works", {"filter": "x", "api_key": "SECRET"}, opener=op, sleep=sleeps.append)
        self.assertEqual(len(calls), up.ATTEMPTS)
        self.assertEqual(len(sleeps), up.ATTEMPTS - 1)
        self.assertNotIn("SECRET", str(e.exception))

    def test_retry_after_is_respected_then_success(self):
        op, calls = self.opener([429, "timeout", 200], headers={"Retry-After": "7"})
        sleeps = []
        self.assertEqual(up.get_json("https://x", {}, opener=op, sleep=sleeps.append), {"ok": True})
        self.assertEqual(sleeps[0], 7)
        self.assertEqual(len(calls), 3)

    def test_long_retry_after_and_client_errors_fail_without_retry(self):
        for codes, headers in (([429], {"Retry-After": "86400"}), ([401], None)):
            op, calls = self.opener(codes, headers)
            with self.assertRaises(up.SourceError):
                up.get_json("https://x", {}, opener=op, sleep=lambda s: None)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
