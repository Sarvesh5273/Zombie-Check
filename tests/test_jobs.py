"""Offline job-path tests against the real pipeline, not live-500 proof.

All employer/ATS documents and datasets below are explicitly synthetic fixtures.
The client has no network transport. run_jobs and Engine.run execute unchanged.
"""
import copy
import datetime as dt
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from zombiecheck.engine import Engine
from zombiecheck.ingest import parse_csv,map_rows
from zombiecheck.jobs import parse_json_page,_read_fields,_board_data,run_jobs
from zombiecheck.store import Store
from tests.test_core import csv_text

FIELDS=("employer","title","job_url","job_id","employer_website","board_url","job_api_url","source_url","listed_updated_at")
BASE="https://boards-api.greenhouse.io/v1/boards/acme"
HOME="https://acme.example"
FEED=BASE+"/jobs?content=true"
STAMP=dt.datetime.now(dt.timezone.utc)


def source(url,body,links=()):
    return {"url":url,"final_url":url,"text":json.dumps(body) if isinstance(body,dict) else body,"links":list(links)}


class JSONPageRegressionTests(unittest.TestCase):
    def test_invalid_markdown_star_and_underscore_escapes_are_repaired(self):
        text=r'{"first\_published":"2026-11-10","content":"one \* two \_ three"}'
        body,error=parse_json_page({"page":{"text":text}})
        self.assertIsNone(error)
        self.assertEqual(body,{"first_published":"2026-11-10","content":"one * two _ three"})

    def test_mixed_invalid_escapes_preserve_newline_unicode_and_quotes(self):
        text=r'{"content":"markup \* and \_","newline":"first\nsecond","unicode":"\u0041","quote":"\"yes\"","literal":"\\n"}'
        body,error=parse_json_page({"page":{"text":text}})
        self.assertIsNone(error)
        self.assertEqual(body["content"],"markup * and _")
        self.assertEqual(body["newline"],"first\nsecond")
        self.assertEqual(body["unicode"],"A")
        self.assertEqual(body["quote"],'"yes"')
        self.assertEqual(body["literal"],r"\n")

    def test_valid_paired_backslash_star_and_underscore_literals_survive(self):
        text=r'{"content":"literal \\* and literal \\_"}'
        expected=json.loads(text)
        body,error=parse_json_page({"page":{"text":text}})
        self.assertIsNone(error)
        self.assertEqual(body,expected)
        self.assertEqual(body["content"],r"literal \* and literal \_")

    def test_paired_literals_survive_mixed_invalid_markdown_escapes(self):
        text=r'{"content":"literal \\*; markup \*; literal \\_; markup \_","unicode":"\uD83D\uDE00"}'
        body,error=parse_json_page({"page":{"text":text}})
        self.assertIsNone(error)
        self.assertEqual(body["content"],r"literal \*; markup *; literal \_; markup _")
        self.assertEqual(body["unicode"],"😀")

    def test_fenced_json_and_dictionary_pages_are_supported(self):
        for entry in ({"page":{"text":"```json\n{\"jobs\": []}\n```"}},
                      {"page":{"text":{"jobs":[]}}}):
            with self.subTest(entry=entry):
                self.assertEqual(parse_json_page(entry),({"jobs":[]},None))

    def test_malformed_unicode_or_nonobject_source_is_not_fabricated(self):
        for text in (r'{"value":"\u12"}',r'{"value":"unterminated}',"[]","not JSON"):
            with self.subTest(text=text):
                body,error=parse_json_page({"page":{"text":text}})
                self.assertIsNone(body)
                self.assertEqual(error["error"],"invalid_json_source")


class JobFixtureClient:
    def __init__(self,ids=(101,),metadata_name="Acme",total=None,questions=True,first_days=5):
        self.ids=list(ids)
        self.pages={}
        self.errors={}
        self.fetch_calls=[]
        self.search_calls=[]
        self.search_results=[]
        self.creates=[]
        self.datasets={}
        self.lock=threading.RLock()
        self.metadata_name=metadata_name
        self.before_fetch=None
        self.first_days=first_days
        self.questions=questions
        self.pages[HOME]=source(HOME,"# Acme\nCompany website",[HOME+"/blog",HOME+"/changelog","https://github.com/acme-fixture"])
        self.pages[HOME+"/blog"]=source(HOME+"/blog","# Blog\nNovember 12, 2026\nCompany announcement")
        self.pages[HOME+"/changelog"]=source(HOME+"/changelog","# Changelog\nNovember 13, 2026\nProduct release")
        self.pages["https://github.com/acme-fixture"]=source("https://github.com/acme-fixture","# Source repository\nNovember 14, 2026\nA published commit")
        self.pages[BASE]=source(BASE,{"name":metadata_name})
        feed={"jobs":[{"id":i,"title":"Engineer "+str(i),"absolute_url":self.job_url(i)} for i in ids],
              "meta":{"total":len(ids) if total is None else total}}
        self.pages[FEED]=source(FEED,feed)
        for id in ids:self.add_role(id)

    @staticmethod
    def job_url(id,modern=False):
        domain="job-boards.greenhouse.io" if modern else "boards.greenhouse.io"
        return f"https://{domain}/acme/jobs/{id}"

    @staticmethod
    def role_url(id):return f"{BASE}/jobs/{id}?questions=true"

    def row(self,id,modern=False):
        return ["Acme","Engineer "+str(id),self.job_url(id,modern),f"greenhouse:acme:{id}",HOME,
                HOME+"/careers",self.role_url(id),FEED,(STAMP-dt.timedelta(days=1)).isoformat()]

    def add_role(self,id,modern=False):
        role={"id":id,"company_name":"Acme","title":"Engineer "+str(id),"absolute_url":self.job_url(id),
              "first_published":(STAMP-dt.timedelta(days=self.first_days)).isoformat(),
              "updated_at":(STAMP-dt.timedelta(days=1)).isoformat(),
              "questions":[{"label":"First Name","fields":[{"type":"input_text","name":"first_name"}]}] if self.questions else []}
        self.pages[self.role_url(id)]=source(self.role_url(id),role)
        public=self.job_url(id,modern)
        self.pages[public]=source(public,"# Engineer "+str(id)+"\nFirst Name\nLast Name\nEmail\nResume\nSubmit application")

    def role_change(self,posting_id,**fields):
        page=self.pages[self.role_url(posting_id)]
        role=json.loads(page["text"])
        role.update(fields)
        page["text"]=json.dumps(role)

    def fetch(self,urls):
        if self.before_fetch:self.before_fetch(urls)
        with self.lock:
            self.fetch_calls.append(list(urls))
            pages,errors=[],[]
            for url in urls:
                if url in self.errors:errors.append(dict(copy.deepcopy(self.errors[url]),url=url))
                elif url in self.pages:pages.append(copy.deepcopy(self.pages[url]))
                else:raise AssertionError("Unexpected fixture URL: "+url)
            return {"results":pages,"errors":errors}

    def search(self,query):
        with self.lock:self.search_calls.append(query)
        return {"results":copy.deepcopy(self.search_results)}

    def create_dataset(self,name,entities):
        with self.lock:
            id="fixture-dataset-"+str(len(self.creates)+1)
            self.creates.append({"name":name,"entities":copy.deepcopy(entities),"id":id})
            self.datasets[id]=copy.deepcopy(entities)
            return {"id":id}

    def find_dataset(self,name):
        found=[r for r in self.creates if r["name"]==name]
        return {"id":found[0]["id"]} if found else None

    def dataset(self,id):return {"status":"ready","run":{"id":"fixture-run","status":"done"}}

    def dataset_rows(self,id):
        return [{"data":{"company":e["name"],"website":e["website"],"blog":HOME+"/blog","release":HOME+"/changelog",
                         "social":"https://github.com/acme-fixture"}} for e in self.datasets[id]]


class RealJobPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def audit(self,client,rows=None):
        parsed=parse_csv(csv_text(rows or [client.row(i) for i in client.ids],FIELDS))
        id=self.store.create_audit(parsed,map_rows(parsed,1,2),"Job pipeline fixture",
            {"mode":"jobs","budget":1,"strategy":"triage","browser_checks":0})
        return id,Engine(self.store,client_factory=lambda _:client)

    def execute_jobs(self,client,rows=None):
        id,engine=self.audit(client,rows)
        run_jobs(engine,id,threading.Event())
        return id,engine,self.store.rows(id)

    def test_actual_engine_run_dispatches_jobs_and_preserves_originals(self):
        client=JobFixtureClient((101,102))
        id,engine=self.audit(client)
        originals=[r["original"] for r in self.store.rows(id)]
        engine.run(id,threading.Event())
        saved=self.store.rows(id)
        self.assertEqual(self.store.audit(id)["status"],"complete")
        self.assertEqual([r["original"] for r in saved],originals)
        self.assertEqual([r["result"]["verdict"] for r in saved],["alive","alive"])
        self.assertEqual(len(client.creates),1)
        self.assertEqual(len(client.creates[0]["entities"]),1)
        self.assertEqual(saved[0]["dataset_id"],saved[1]["dataset_id"])
        self.assertTrue(all(r["result"]["signals_checked"]==5 for r in saved))
        self.assertTrue(all(r["result"]["signals"]["blog"]["shared"] for r in saved))
        self.assertTrue(all(r["result"]["signals"]["jobs"]["shared"] is False for r in saved))
        self.assertTrue(all("unverified" in r["result"]["reason"] for r in saved))
        self.assertFalse(engine.report(id)["submission_ready"],"Two synthetic fixture roles cannot prove a live500 run")

    def test_complete_board_and_metadata_match(self):
        client=JobFixtureClient((101,102))
        id,engine=self.audit(client)
        row=self.store.rows(id)[0]
        values=_read_fields(self.store.audit(id),row)
        board=_board_data(engine,id,values,client)
        self.assertTrue(board["complete"])
        self.assertEqual(board["ids"],{"101","102"})

    def test_partial_total_mismatch_cannot_confirm_dead_posting(self):
        client=JobFixtureClient((102,),total=2)
        client.errors[client.role_url(101)]={"error":"page_not_found","status":404}
        client.errors[client.job_url(101)]={"error":"page_not_found","status":404}
        id,engine,rows=self.execute_jobs(client,[client.row(101)])
        self.assertEqual(rows[0]["status"],"review")
        self.assertNotEqual(rows[0]["result"]["verdict"],"zombie")
        self.assertFalse(rows[0]["result"]["board_check"]["complete"])

    def test_wrong_board_employer_metadata_requires_review(self):
        client=JobFixtureClient(metadata_name="OtherCo")
        _,_,rows=self.execute_jobs(client)
        self.assertEqual(rows[0]["status"],"review")
        self.assertEqual(rows[0]["error"],"employer_board_mismatch")

    def test_source_board_or_provider_token_mismatch_rejected_before_research(self):
        for field,value in (("source_url","https://boards-api.greenhouse.io/v1/boards/other/jobs?content=true"),
                            ("job_id","greenhouse:other:101"),
                            ("job_api_url","https://boards-api.greenhouse.io/v1/boards/other/jobs/101?questions=true")):
            with self.subTest(field=field):
                client=JobFixtureClient()
                row=client.row(101)
                row[FIELDS.index(field)]=value
                _,_,rows=self.execute_jobs(client,[row])
                self.assertEqual(rows[0]["status"],"review")
                self.assertEqual(client.creates,[])
                self.assertEqual(client.fetch_calls,[])

    def test_live_role_id_employer_or_canonical_url_mismatch_requires_review(self):
        for change in ({"id":999},{"company_name":"OtherCo"},{"absolute_url":JobFixtureClient.job_url(999)},
                       {"absolute_url":"https://unrelated.example/jobs/101"}):
            with self.subTest(change=change):
                client=JobFixtureClient()
                client.role_change(101,**change)
                _,_,rows=self.execute_jobs(client)
                self.assertEqual(rows[0]["status"],"review")
                self.assertEqual(rows[0]["error"],"posting_identity_mismatch")

    def test_legacy_and_current_greenhouse_job_hosts_are_same_exact_role(self):
        client=JobFixtureClient()
        client.add_role(101,modern=True)
        _,_,rows=self.execute_jobs(client,[client.row(101,modern=True)])
        self.assertEqual(rows[0]["status"],"done")
        self.assertEqual(rows[0]["result"]["verdict"],"alive")
        self.assertTrue(rows[0]["result"]["public_page_check"]["matched_posting"])

    def test_unrelated_public_redirect_cannot_supply_original_role_form_evidence(self):
        client=JobFixtureClient()
        client.pages[client.job_url(101)]["final_url"]="https://unrelated.example/jobs/101"
        _,_,rows=self.execute_jobs(client)
        result=rows[0]["result"]
        self.assertFalse(result["public_page_check"]["matched_posting"])
        self.assertFalse(result["public_page_check"]["application_form_text_found"])
        self.assertNotEqual(result["signals"]["signup"]["url"],"https://unrelated.example/jobs/101")

    def test_default404_with_metadata_localized200_keeps_original_evidence(self):
        for language in ("ja","ko"):
            with self.subTest(language=language):
                client=JobFixtureClient()
                original=HOME+"/detail/101/?gh_jid=101"
                localized=HOME+f"/{language}/detail/101/?gh_jid=101"
                client.role_change(101,absolute_url=original,language=language)
                client.errors[original]={"error":"page_not_found","status":404}
                client.pages[localized]=source(localized,"# Engineer 101\nFirst Name\nLast Name\nEmail\nResume\nSubmit application")
                input_row=client.row(101)
                input_row[FIELDS.index("job_url")]=original
                id,_,rows=self.execute_jobs(client,[input_row])
                result=rows[0]["result"]
                self.assertEqual(rows[0]["status"],"done")
                self.assertEqual(result["verdict"],"alive")
                self.assertEqual(rows[0]["original"],input_row)
                self.assertIn(localized,result["evidence_links"])
                self.assertTrue(any(localized in call for call in client.fetch_calls))
                self.assertEqual(self.store.snapshot(id,original)["error"]["status"],404)

    def test_unrelated_localized_page_cannot_resolve_default404(self):
        client=JobFixtureClient()
        original=HOME+"/detail/101/?gh_jid=101"
        localized=HOME+"/ja/detail/101/?gh_jid=101"
        client.role_change(101,absolute_url=original,language="ja")
        client.errors[original]={"error":"page_not_found","status":404}
        client.pages[localized]=source(localized,"# Engineer 999\nFirst Name\nLast Name\nEmail\nResume\nSubmit application")
        input_row=client.row(101)
        input_row[FIELDS.index("job_url")]=original
        _,_,rows=self.execute_jobs(client,[input_row])
        self.assertEqual(rows[0]["status"],"review")
        self.assertEqual(rows[0]["result"]["verdict"],"")

    def test_metadata_en_can_use_exact_indexed_ja_route_without_guessing_locale(self):
        client=JobFixtureClient()
        original=HOME+"/detail/101/?gh_jid=101"
        english=HOME+"/en/detail/101/?gh_jid=101"
        japanese=HOME+"/ja/detail/101/?gh_jid=101"
        client.role_change(101,absolute_url=original,language="en",location={"name":"Tokyo"})
        for url in (original,english):client.errors[url]={"error":"page_not_found","status":404}
        client.pages[japanese]=source(japanese,"# Engineer 101\nTokyo\nFirst Name\nLast Name\nEmail\nResume\nSubmit application")
        client.search_results=[{"url":japanese,"title":"Engineer 101 — Tokyo","snippet":"Official Acme role"}]
        input_row=client.row(101)
        input_row[FIELDS.index("job_url")]=original
        id,_,rows=self.execute_jobs(client,[input_row])
        self.assertEqual(rows[0]["status"],"done")
        self.assertEqual(rows[0]["result"]["verdict"],"alive")
        self.assertTrue(client.search_calls)
        self.assertIn(japanese,rows[0]["result"]["evidence_links"])
        self.assertEqual(rows[0]["original"],input_row)
        self.assertEqual(self.store.snapshot(id,original)["error"]["status"],404)

    def test_indexed_fallback_rejects_wrong_host_or_posting_id_before_fetch(self):
        for wrong in ("https://unrelated.example/ja/detail/101/?gh_jid=101",
                      HOME+"/ja/detail/999/?gh_jid=999"):
            with self.subTest(wrong=wrong):
                client=JobFixtureClient()
                original=HOME+"/detail/101/?gh_jid=101"
                english=HOME+"/en/detail/101/?gh_jid=101"
                client.role_change(101,absolute_url=original,language="en",location={"name":"Tokyo"})
                for url in (original,english):client.errors[url]={"error":"page_not_found","status":404}
                client.search_results=[{"url":wrong,"title":"Engineer 101 — Tokyo"}]
                input_row=client.row(101)
                input_row[FIELDS.index("job_url")]=original
                _,_,rows=self.execute_jobs(client,[input_row])
                self.assertEqual(rows[0]["status"],"review")
                self.assertEqual(rows[0]["result"]["verdict"],"")
                self.assertFalse(any(wrong in call for call in client.fetch_calls))

    def test_mismatched_gh_jid_cannot_redirect_original_role_identity(self):
        client=JobFixtureClient()
        row=client.row(101)
        row[FIELDS.index("job_url")]+="?gh_jid=999"
        _,_,rows=self.execute_jobs(client,[row])
        self.assertEqual(rows[0]["status"],"review")
        self.assertEqual(client.creates,[])

    def test_complete_board_absence_and_direct404_confirm_zombie_posting(self):
        client=JobFixtureClient((102,))
        client.errors[client.role_url(101)]={"error":"page_not_found","status":404}
        client.errors[client.job_url(101)]={"error":"page_not_found","status":404}
        _,_,rows=self.execute_jobs(client,[client.row(101)])
        result=rows[0]["result"]
        self.assertEqual(rows[0]["status"],"done")
        self.assertEqual(result["verdict"],"zombie")
        self.assertTrue(result["board_check"]["complete"])
        self.assertEqual(result["signals"]["jobs"]["absence_evidence"]["posting_id"],"101")
        self.assertIn(FEED,result["evidence_links"])

    def test_blocked_or_timed_out_role_api_never_means_zombie(self):
        for error,status in (("target_http_error",403),("bot_blocked",None),("timeout",None)):
            with self.subTest(error=error):
                client=JobFixtureClient()
                client.errors[client.role_url(101)]={"error":error,"status":status}
                _,_,rows=self.execute_jobs(client)
                self.assertEqual(rows[0]["status"],"review")
                self.assertNotEqual(rows[0]["result"]["verdict"],"zombie")

    def test_api_present_but_public_page404_or_closed_is_source_conflict(self):
        for closed in (False,True):
            with self.subTest(explicit_closed=closed):
                client=JobFixtureClient()
                if closed:client.pages[client.job_url(101)]=source(client.job_url(101),"This job is no longer available. No longer accepting applications.")
                else:client.errors[client.job_url(101)]={"error":"page_not_found","status":404}
                _,_,rows=self.execute_jobs(client)
                self.assertEqual(rows[0]["status"],"review")
                self.assertEqual(rows[0]["result"]["verdict"],"")

    def test_old_first_published_is_stale_even_if_updated_recently(self):
        client=JobFixtureClient(first_days=121)
        client.role_change(101,updated_at=(STAMP-dt.timedelta(minutes=1)).isoformat())
        _,_,rows=self.execute_jobs(client)
        result=rows[0]["result"]
        self.assertEqual(result["verdict"],"slowing down")
        self.assertGreater(result["job_age_days"],90)
        self.assertEqual(result["job_first_published"],(STAMP-dt.timedelta(days=121)).isoformat())

    def test_missing_application_questions_requires_review(self):
        client=JobFixtureClient(questions=False)
        _,_,rows=self.execute_jobs(client)
        self.assertEqual(rows[0]["status"],"review")
        self.assertEqual(rows[0]["result"]["verdict"],"")
        self.assertEqual(rows[0]["error"],"intake_not_configured")

    def test_resume_does_not_reprocess_done_roles_or_duplicate_employer_dataset(self):
        client=JobFixtureClient((101,102))
        id,engine,rows=self.execute_jobs(client)
        creates=len(client.creates)
        calls=len(client.fetch_calls)
        dataset_ids=[r["dataset_id"] for r in rows]
        reserved=self.store.audit(id)["reserved"]
        run_jobs(Engine(self.store,client_factory=lambda _:client),id,threading.Event())
        self.assertEqual(len(client.creates),creates)
        self.assertEqual(len(client.fetch_calls),calls)
        self.assertEqual([r["dataset_id"] for r in self.store.rows(id)],dataset_ids)
        self.assertAlmostEqual(self.store.audit(id)["reserved"],reserved)

    def test_resume_completes_failed_role_without_rechecking_completed_one(self):
        client=JobFixtureClient((101,102))
        client.errors[client.role_url(102)]={"error":"timeout"}
        id,engine,rows=self.execute_jobs(client)
        self.assertEqual([r["status"] for r in rows],["done","review"])
        first_fetches=sum(client.role_url(101) in call for call in client.fetch_calls)
        del client.errors[client.role_url(102)]
        run_jobs(Engine(self.store,client_factory=lambda _:client),id,threading.Event())
        self.assertEqual([r["status"] for r in self.store.rows(id)],["done","done"])
        self.assertEqual(sum(client.role_url(101) in call for call in client.fetch_calls),first_fetches)
        self.assertEqual(len(client.creates),1)


if __name__=="__main__":unittest.main()
