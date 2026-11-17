"""Offline regression tests. These fixtures are not a real-world bounty demo."""
import csv
import datetime as dt
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from zombiecheck.engine import Engine
from zombiecheck.evidence import (apply_identity_evidence, identity_from_page,
                                 observe_page, verify_claim)
from zombiecheck.ingest import export_csv, map_rows, parse_csv
from zombiecheck.models import SIGNALS, activity_date, dated_activity, safe_url, utcnow
from zombiecheck.rules import classify
from zombiecheck.store import Store
from zombiecheck.tinyfish import APIError, TinyFish

TODAY = dt.date(2026, 11, 17)


def csv_text(rows, headers=("company", "website", "notes")):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()


def records(status="unknown", verified=False, date=None, date_verified=False):
    return {kind: {"kind": kind, "status": status, "verified": verified,
                   "date_verified": date_verified, "latest_date": date,
                   "checked_at": "2026-11-17T10:00:00+00:00",
                   "url": "https://acme.example/" + kind,
                   "quote": "Observed source text"}
            for kind in SIGNALS}


def page(text, url="https://acme.example", final_url=None, links=()):
    return {"url": url, "final_url": final_url or url, "text": text,
            "links": list(links), "checked_at": "2026-11-17T10:00:00+00:00"}


def result_fixture():
    signals = records("inactive", True)
    signals["signup"].update(status="active")
    return classify(signals, {"status": "same", "verified": True,
                    "url": "https://acme.example", "canonical_url": "https://acme.example"},
                    {"verified": True, "url": "https://acme.example"}, today=TODAY)


class CSVFidelityTests(unittest.TestCase):
    def test_523_rows_unicode_multiline_quotes_order_and_duplicates(self):
        source_rows = [["Company " + str(i % 519), "https://c%s.example" % (i % 519),
                        '  café 東京, "quoted"\nsecond line  '] for i in range(523)]
        parsed = parse_csv(csv_text(source_rows))
        mapped = map_rows(parsed, 0, 1)
        for item in mapped:
            item.update(status="pending", result=None)
        exported = list(csv.reader(io.StringIO(export_csv(parsed["headers"], mapped))))
        self.assertEqual(len(exported) - 1, 523)
        self.assertEqual(exported[0][:3], list(("company", "website", "notes")))
        self.assertEqual([row[:3] for row in exported[1:]], source_rows)
        row_id_column = exported[0].index("row_id")
        self.assertEqual([r[row_id_column] for r in exported[1:]], ["R%06d" % (i + 1) for i in range(523)])

    def test_added_columns_do_not_overwrite_collisions(self):
        parsed = parse_csv(csv_text([["Acme", "original verdict", "original collision"]],
                                    ("company", "verdict", "zc_verdict")))
        row = map_rows(parsed, 0, None)[0]
        row.update(status="done", result=result_fixture())
        out = list(csv.reader(io.StringIO(export_csv(parsed["headers"], [row]))))
        self.assertEqual(out[1][1:3], ["original verdict", "original collision"])
        self.assertIn("zc_zc_verdict", out[0])
        self.assertEqual(len(set(out[0])), len(out[0]))

    def test_rejects_duplicate_headers(self):
        with self.assertRaises(ValueError):
            parse_csv("name,name\nAcme,other\n")

    def test_rejects_ragged_rows_without_losing_cells(self):
        with self.assertRaises(ValueError):
            parse_csv("company,website\nAcme,https://acme.example,extra\n")

    def test_bom_semicolon_and_blank_cell_preserved(self):
        parsed = parse_csv('\ufeffcompany;website;note\r\nAcme;https://acme.example;\r\n')
        self.assertEqual(parsed["rows"], [["Acme", "https://acme.example", ""]])

    def test_unknown_name_column_is_mappable(self):
        parsed = parse_csv("custom label,custom domain\nAcme,acme.example\n")
        mapped = map_rows(parsed, 0, 1)
        self.assertEqual(mapped[0]["website"], "https://acme.example")


class EvidenceAccuracyTests(unittest.TestCase):
    def test_future_and_footer_dates_rejected(self):
        self.assertIsNone(activity_date("2027-01-01", TODAY))
        self.assertIsNone(dated_activity("© Copyright 2026-11-17, all rights reserved"))
        self.assertEqual(dated_activity("Release notes\nNovember 10, 2026 — New API"), "2026-11-10")

    def test_policy_effective_date_is_not_product_activity(self):
        self.assertIsNone(dated_activity("Privacy Policy\nEffective date: November 10, 2026\nContact us"))

    def test_unsupported_exact_date_not_verified(self):
        claim = {"status": "active", "latest_date": "2026-11-01", "url": "https://acme.example/blog",
                 "quote": "A useful product update"}
        observed = verify_claim(claim, page("A useful product update\nOCT 2026"), "blog")
        self.assertFalse(observed["date_verified"])

    def test_fabricated_quote_rejected(self):
        claim = {"status": "active", "url": "https://acme.example/blog", "quote": "We shipped a thousand features"}
        observed = verify_claim(claim, page("Our website home page"), "blog")
        self.assertFalse(observed["verified"])
        self.assertEqual(observed["error"], "quote_not_on_page")

    def test_newsletter_is_not_product_signup(self):
        observed = observe_page("signup", "https://acme.example/signup",
                                page("Acme builds enterprise tools.\nSign up for our newsletter\nEmail address\nSubscribe"))
        self.assertNotEqual(observed["status"], "active")
        self.assertFalse(observed["verified"])

    def test_unrelated_redirect_is_not_working_original_signup(self):
        observed = observe_page("signup", "https://acme.example/signup",
                                page("Create your account\nPassword\nContinue", final_url="https://unrelated.example/register"))
        self.assertNotEqual(observed["status"], "active")

    def test_dated_copyright_footer_does_not_make_release_active(self):
        observed = observe_page("release", "https://acme.example/changelog",
                                page("Changelog\nNo updates to show\n© Copyright 2026-11-17"))
        self.assertIsNone(observed["latest_date"])
        self.assertNotEqual(observed["status"], "active")

    def test_no_jobs_is_negative_but_not_closure(self):
        observed = observe_page("jobs", "https://acme.example/careers", page("No open positions"))
        self.assertEqual(observed["status"], "inactive")
        self.assertTrue(observed["verified"])

    def test_unlinked_social_profile_not_verified_as_no_social(self):
        observed = observe_page("social", "https://github.com/foreign-owner", page("ForeignOwner\nNovember 12, 2026"), linked=False)
        self.assertFalse(observed["verified"])

    def test_blog_sidebar_external_article_not_official_activity(self):
        observed = observe_page("blog", "https://foreign.example/blog", page("Other company's article\nNovember 10, 2026", url="https://foreign.example/blog"), linked=False)
        # The extraction cannot independently establish ownership. Do not mark it as verified company life.
        self.assertFalse(observed["verified"])

    def test_failure_types_do_not_become_verified_inactivity(self):
        for code in ("timeout", "bot_blocked", "target_unreachable", "login_required", "target_http_error"):
            with self.subTest(code=code):
                observed = observe_page("signup", "https://acme.example/signup", error={"error": code, "status": 403})
                self.assertFalse(observed["verified"])
                self.assertNotEqual(observed["status"], "inactive")

    def test_404_proves_missing_url_only(self):
        observed = observe_page("blog", "https://acme.example/blog", error={"error": "page_not_found", "status": 404})
        self.assertEqual(observed["status"], "not_found")
        result = classify({kind: dict(observed, kind=kind) for kind in SIGNALS},
                          {"status": "unknown", "verified": False}, today=TODAY)
        self.assertNotEqual(result["verdict"], "zombie")

    def test_generic_shutdown_mention_does_not_close_company(self):
        row = {"name": "Acme", "website": "https://acme.example"}
        identity = {"status": "same", "verified": True, "canonical_url": row["website"]}
        closure = apply_identity_evidence(row, identity, page("Acme announces a new product.\nRead our guide to handling a graceful shutdown of your application."))
        self.assertIsNone(closure)

    def test_another_company_shutdown_does_not_close_subject(self):
        row = {"name": "Acme", "website": "https://acme.example"}
        identity = {"status": "same", "verified": True, "canonical_url": row["website"]}
        closure = apply_identity_evidence(row, identity,
                    page("Acme is a thriving company.\nOur customer OtherCo has shut down its business."))
        self.assertIsNone(closure)

    def test_homepage_customer_quote_does_not_close_company(self):
        row = {"name": "Acme", "website": "https://acme.example"}
        observed = identity_from_page(row, page('Acme warehouse management software.\nCustomer testimonial: "We are closing a warehouse and using Acme."'))
        self.assertNotEqual(observed["status"], "closed")

    def test_first_person_explicit_company_closure_supported(self):
        row = {"name": "Acme", "website": "https://acme.example"}
        observed = identity_from_page(row, page("Acme\nWe have shut down our business and ceased operations. Thank you."))
        self.assertEqual(observed["status"], "closed")

    def test_parent_redirect_remains_ambiguous(self):
        row = {"name": "OldProduct", "website": "https://oldproduct.example"}
        observed = identity_from_page(row, page("ParentCompany — create an account", url=row["website"], final_url="https://parent.example"))
        self.assertEqual(observed["status"], "ambiguous")
        self.assertFalse(observed["verified"])


class VerdictTests(unittest.TestCase):
    def test_blocked_sites_do_not_become_zombies(self):
        result = classify(records("blocked", False), {"status": "unknown", "verified": False}, today=TODAY)
        self.assertNotEqual(result["verdict"], "zombie")
        self.assertTrue(result["review_required"])

    def test_closure_conflicting_with_active_signup_requires_review(self):
        signals = records("unknown", False)
        signals["signup"].update(status="active", verified=True)
        closure = {"status": "confirmed", "verified": True, "url": "https://acme.example/closure"}
        result = classify(signals, {"status": "same", "verified": True}, {"verified": True}, closure=closure, today=TODAY)
        self.assertTrue(result["review_required"])
        self.assertNotEqual(result["verdict"], "zombie")

    def test_fewer_than_four_finished_checks_withholds_verdict(self):
        signals = records("active", True, "2026-11-10", True)
        signals["jobs"]["checked_at"] = None
        signals["social"]["checked_at"] = None
        result = classify(signals, {"status": "same", "verified": True}, today=TODAY)
        self.assertEqual(result["verdict"], "")

    def test_recent_verified_product_activity_alive(self):
        signals = records("unknown", False)
        signals["release"].update(status="active", verified=True, latest_date="2026-11-10", date_verified=True)
        result = classify(signals, {"status": "same", "verified": True}, today=TODAY)
        self.assertEqual(result["verdict"], "alive")
        self.assertEqual(result["latest_activity_date"], "2026-11-10")

    def test_stale_operating_company_slows_without_becoming_zombie(self):
        signals = records("unknown", False)
        signals["release"].update(status="active", verified=True, latest_date="2024-11-10", date_verified=True)
        result = classify(signals, {"status": "same", "verified": True}, {"verified": True}, today=TODAY)
        self.assertEqual(result["verdict"], "slowing down")

    def test_two_active_signals_on_same_exact_page_not_independent(self):
        signals = records("unknown", False)
        for kind in ("blog", "social"):
            signals[kind].update(status="active", verified=True,
                                 url="https://acme.example/shared-page")
        result = classify(signals, {"status": "same", "verified": True}, today=TODAY)
        self.assertNotEqual(result["verdict"], "alive")
        self.assertTrue(result["review_required"])

    def test_verified_date_cannot_be_copyright_even_if_quote_matches(self):
        claim = {"status": "active", "latest_date": "2026-11-17",
                 "url": "https://acme.example/blog", "quote": "Acme creates useful tools"}
        observed = verify_claim(claim, page("Acme creates useful tools\n© Copyright 2026-11-17"), "blog")
        self.assertFalse(observed["date_verified"])

    def test_pure_parent_company_activity_does_not_reanimate_acquired_product(self):
        signals = records("active", True, "2026-11-10", True)
        result = classify(signals, {"status": "ambiguous", "verified": False}, {"verified": True}, today=TODAY)
        self.assertTrue(result["review_required"])
        self.assertNotEqual(result["verdict"], "alive")


class StoreEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name) / "audit.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def create(self, rows=None, budget=5, strategy="triage"):
        parsed = parse_csv(csv_text(rows or [["Acme", "https://acme.example", ""]]))
        mapped = map_rows(parsed, 0, 1)
        return self.store.create_audit(parsed, mapped, "Fixture audit", {"budget": budget, "strategy": strategy}), mapped

    def test_budget_reservations_atomic_and_capped(self):
        id, _ = self.create(budget=1)
        outcomes = []
        threads = [threading.Thread(target=lambda: outcomes.append(self.store.reserve(id, 0.6))) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sum(outcomes), 1)
        self.assertAlmostEqual(self.store.audit(id)["reserved"], 0.6)

    def test_negative_reservation_cannot_increase_spendable_budget(self):
        id, _ = self.create(budget=1)
        with self.assertRaises(ValueError):
            self.store.reserve(id, -10)

    def test_saved_snapshot_reused_within_same_audit_not_other_audit(self):
        id, _ = self.create()
        other, _ = self.create()
        self.store.snapshot(id, "https://acme.example", {"page": page("Acme")})
        self.assertIsNotNone(self.store.snapshot(id, "https://acme.example"))
        self.assertIsNone(self.store.snapshot(other, "https://acme.example"))

    def test_resume_does_not_reprocess_completed_rows(self):
        id, mapped = self.create(rows=[["Done", "https://done.example", ""], ["Pending", "https://pending.example", ""]], budget=0)
        self.store.row_update(id, mapped[0]["row_id"], status="done", result=result_fixture())
        visited = []
        engine = Engine(self.store, client_factory=lambda _: object())
        def finish(audit_id, row, client, stop, raw=None):
            visited.append(row["row_id"])
            self.store.row_update(id, row["row_id"], status="done", result=result_fixture())
        engine.fast_row = finish
        engine.run(id, threading.Event())
        self.assertEqual(visited, [mapped[1]["row_id"]])

    def test_resume_retries_transient_review_failure(self):
        id, mapped = self.create(budget=0)
        self.store.row_update(id, mapped[0]["row_id"], status="review", error="timeout", result={"verdict": "", "review_required": True})
        visited = []
        engine = Engine(self.store, client_factory=lambda _: object())
        engine.fast_row = lambda audit_id, row, client, stop, raw=None: visited.append(row["row_id"])
        engine.run(id, threading.Event())
        self.assertEqual(visited, [mapped[0]["row_id"]])

    def test_deduplicated_research_fans_out_to_original_duplicates(self):
        id, mapped = self.create(rows=[["Acme", "https://acme.example", "first"], ["Acme", "https://acme.example", "duplicate"]], strategy="full")
        engine = Engine(self.store, client_factory=lambda _: object())
        engine.create_batches(id, self.store.rows(id))
        batch = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        client = DatasetClient([{"data": {"company": "Acme", "website": "https://acme.example"}}])
        visited = []
        def finish(audit_id, row, client, stop, raw=None):
            visited.append(row["row_id"])
            self.store.row_update(id,row["row_id"],status="done",result=result_fixture())
        engine.fast_row = finish
        engine.batch(id, batch, client, threading.Event())
        self.assertEqual(client.created, 1)
        self.assertAlmostEqual(self.store.audit(id)["reserved"], 0.10)
        saved = self.store.rows(id)
        self.assertEqual(saved[0]["result"], saved[1]["result"])
        self.assertEqual(saved[0]["raw"], saved[1]["raw"])
        self.assertEqual(saved[0]["dataset_id"], saved[1]["dataset_id"])
        self.assertIsNotNone(saved[1]["dataset_id"])
        self.assertEqual([r["original"] for r in saved], [r["original"] for r in mapped])
        self.assertEqual(self.store.audit(id)["counts"].get("done"), 2)

    def test_unexpected_tinyset_entity_is_rejected(self):
        id, mapped = self.create(strategy="full")
        engine = Engine(self.store)
        engine.create_batches(id, self.store.rows(id))
        batch = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        visited = []
        engine.fast_row = lambda audit_id, row, client, stop, raw=None: visited.append(row["row_id"])
        engine.batch(id,batch,DatasetClient([{"data": {"company": "OtherCo", "website": "https://other.example"}}]),threading.Event())
        self.assertEqual(visited, [])
        self.assertIsNotNone(self.store.rows(id)[0]["error"])

    def test_same_name_wrong_domain_is_rejected(self):
        id, _ = self.create(strategy="full")
        engine = Engine(self.store)
        engine.create_batches(id, self.store.rows(id))
        batch = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        visited = []
        engine.fast_row = lambda audit_id, row, client, stop, raw=None: visited.append(row["row_id"])
        engine.batch(id,batch,DatasetClient([{"data": {"company": "Acme", "website": "https://other.example"}}]),threading.Event())
        self.assertEqual(visited, [])

    def test_remote_creation_ambiguity_never_blindly_repeats_charge(self):
        id, _ = self.create(strategy="full")
        engine = Engine(self.store)
        engine.create_batches(id,self.store.rows(id))
        batch = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        client = DatasetClient([])
        client.create_error = APIError(0, "Connection dropped after create", ambiguous=True)
        engine.batch(id,batch,client,threading.Event())
        saved = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        engine.batch(id,saved,client,threading.Event())
        self.assertEqual(client.created,1)
        self.assertEqual(client.recoveries,1)

    def test_remote_run_id_reused_on_resume(self):
        id, _ = self.create(strategy="full")
        engine = Engine(self.store)
        engine.create_batches(id,self.store.rows(id))
        batch = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        self.store.execute("UPDATE batches SET dataset_id=?,status='running' WHERE id=?", ("existing-remote",batch["id"]))
        batch = self.store.query("SELECT * FROM batches WHERE audit_id=?", (id,))[0]
        client = DatasetClient([])
        engine.batch(id,batch,client,threading.Event())
        self.assertEqual(client.created,0)
        self.assertEqual(client.polled,["existing-remote"])

    def test_definite_rate_limit_failure_can_resume(self):
        id, mapped = self.create(strategy="full")
        client = DatasetClient([{"data": {"company": "Acme", "website": "https://acme.example"}}])
        engine = Engine(self.store, client_factory=lambda _: client)
        def finish(audit_id,row,client,stop,raw=None):
            self.store.row_update(id,row["row_id"],status="done",result=result_fixture())
        engine.fast_row = finish
        client.create_error = APIError(429,"Temporary concurrency limit",ambiguous=False,retry_after=0)
        engine.run(id,threading.Event())
        self.assertNotEqual(self.store.rows(id)[0]["status"],"done")
        client.create_error = None
        engine.run(id,threading.Event())
        self.assertEqual(self.store.rows(id)[0]["status"],"done")
        self.assertAlmostEqual(self.store.audit(id)["reserved"],0.10)

    def test_partial_remote_result_can_resume_missing_rows(self):
        id, mapped = self.create(rows=[["Acme","https://acme.example","first"],
                                       ["Beta","https://beta.example","second"]],strategy="full")
        client = DatasetClient([{"data": {"company":"Acme","website":"https://acme.example"}}])
        engine = Engine(self.store, client_factory=lambda _: client)
        checked=[]
        def finish(audit_id,row,client,stop,raw=None):
            checked.append(row["row_id"])
            self.store.row_update(id,row["row_id"],status="done",result=result_fixture())
        engine.fast_row=finish
        engine.run(id,threading.Event())
        self.assertEqual(self.store.rows(id)[0]["status"],"done")
        client.rows=[{"data":{"company":"Acme","website":"https://acme.example"}},
                     {"data":{"company":"Beta","website":"https://beta.example"}}]
        engine.run(id,threading.Event())
        self.assertEqual(self.store.audit(id)["counts"].get("done"),2)
        self.assertEqual(checked.count(mapped[0]["row_id"]),1)

    def test_report_rejects_unfinished_500_rows(self):
        id, _ = self.create(rows=[["Company " + str(i), "https://c%s.example" % i, ""] for i in range(500)], budget=0)
        report = Engine(self.store).report(id)
        self.assertEqual(report["input_rows"],500)
        self.assertFalse(report["submission_ready"])
        self.assertFalse(report["gates"]["all_rows_have_verdicts"])

    def test_report_cannot_pass_when_claims_have_no_evidence(self):
        id, mapped = self.create(rows=[["Company " + str(i), "https://c%s.example" % i, ""] for i in range(500)], budget=0)
        for row in mapped:
            self.store.row_update(id,row["row_id"],status="done",result={"verdict":"alive","review_required":False,"signals_checked":5,"evidence_links":[]})
        self.store.execute("INSERT INTO calls(audit_id,time,service,operation,status,units) VALUES(?,?,?,?,?,?)",(id,utcnow(),"tinyset","POST",202,500))
        self.assertFalse(Engine(self.store).report(id)["submission_ready"])

    def test_report_detects_original_cell_corruption_and_withholds_readiness(self):
        original_rows = [["Company " + str(i), "https://c%s.example" % i,
                          '  café 東京, "quoted"\nsecond line  '] for i in range(500)]
        id, mapped = self.create(rows=original_rows, budget=0)
        complete_result = {"verdict": "alive", "review_required": False,
                           "signals_checked": 5,
                           "evidence_links": ["https://acme.example/release"],
                           "signals": records("active", True, "2026-11-10", True)}
        for row in mapped:
            self.store.row_update(id, row["row_id"], status="done", result=complete_result)
        self.store.execute(
            "INSERT INTO calls(audit_id,time,service,operation,status,units) VALUES(?,?,?,?,?,?)",
            (id, utcnow(), "tinyset", "POST", 202, 500))
        engine = Engine(self.store)
        expected_hash = self.store.audit(id)["config"]["original_rows_sha256"]
        before = engine.report(id)
        self.assertTrue(before["gates"]["original_rows_preserved"])
        self.assertTrue(before["submission_ready"])

        corrupted_cells = original_rows[0][:]
        corrupted_cells[2] = "corrupted stored note"
        self.store.execute("UPDATE rows SET original=? WHERE audit_id=? AND row_id=?",
                           (json.dumps(corrupted_cells), id, "R000001"))

        after = engine.report(id)
        self.assertEqual(self.store.audit(id)["config"]["original_rows_sha256"], expected_hash)
        self.assertFalse(after["gates"]["original_rows_preserved"])
        self.assertFalse(after["submission_ready"])
        self.assertTrue(all(value for key, value in after["gates"].items()
                            if key != "original_rows_preserved"))


class DatasetClient:
    def __init__(self, rows):
        self.rows = rows
        self.created = 0
        self.recoveries = 0
        self.polled = []
        self.create_error = None
    def create_dataset(self,name,entities):
        self.created += 1
        if self.create_error: raise self.create_error
        return {"id":"remote-fixture"}
    def find_dataset(self,name):
        self.recoveries += 1
        return None
    def dataset(self,id):
        self.polled.append(id)
        return {"status":"ready","run":{"id":"run-fixture","status":"done"}}
    def dataset_rows(self,id): return self.rows


class ClientContractTests(unittest.TestCase):
    def test_fetch_always_requests_live_sources_and_batches_limit(self):
        client = TinyFish(key="test-key")
        requests = []
        client.request = lambda method,url,body=None,**kw: requests.append((method,url,body,kw)) or {"results":[],"errors":[]}
        client.fetch(["https://acme.example"])
        self.assertEqual(requests[0][2]["ttl"],0)
        with self.assertRaises(ValueError): client.fetch(["https://c%s.example" % i for i in range(11)])

    def test_safe_urls_block_credentials_local_and_metadata(self):
        for url in ("http://127.0.0.1", "http://10.1.2.3", "https://localhost", "http://169.254.169.254", "https://u:p@acme.example", "file:///tmp/a"):
            self.assertEqual(safe_url(url),"")

    def test_unknown_scheme_cannot_be_silently_rewritten(self):
        self.assertEqual(safe_url("javascript:alert(1)"),"")


if __name__=="__main__": unittest.main()
