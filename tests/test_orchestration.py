"""Drive real fast_row with an offline TinyFetch/TinySearch transport fixture.

These tests exercise orchestration and persistence rather than replacing the
pipeline method. Fixture source pages are synthetic and are not demo evidence.
"""
import copy
import tempfile
import threading
import unittest
from pathlib import Path

from zombiecheck.engine import Engine
from zombiecheck.evidence import observe_page
from zombiecheck.ingest import map_rows, parse_csv
from zombiecheck.models import SIGNALS
from zombiecheck.store import Store
from tests.test_core import csv_text


class FixtureWeb:
    """Only returns declared pages; an unexpected fetch is an explicit failure."""
    def __init__(self,pages=None,errors=None,search_results=None):
        self.pages=pages or {}
        self.errors=errors or {}
        self.search_results=search_results or []
        self.fetch_calls=[]
        self.search_calls=[]

    def fetch(self,urls):
        self.fetch_calls.append(list(urls))
        results,errors=[],[]
        for url in urls:
            if url in self.pages:
                results.append(copy.deepcopy(self.pages[url]))
            elif url in self.errors:
                errors.append(dict(copy.deepcopy(self.errors[url]),url=url))
            else:
                raise AssertionError("Undeclared fixture URL fetched: "+url)
        return {"results":results,"errors":errors}

    def search(self,query):
        self.search_calls.append(query)
        return {"results":copy.deepcopy(self.search_results)}


def source(url,text,links=(),title=None,published_date=None):
    return {"url":url,"final_url":url,"text":text,"links":list(links),
            "title":title,"published_date":published_date}


class FastRowOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def audit(self,name="Acme",website="https://acme.example",reference=None):
        headers=("company","website","source_url") if reference else ("company","website","notes")
        original=[name,website,reference or "Original cell remains intact"]
        parsed=parse_csv(csv_text([original],headers))
        id=self.store.create_audit(parsed,map_rows(parsed,0,1),"Orchestration fixture",
                                   {"budget":0,"strategy":"triage","browser_checks":0})
        return id,self.store.rows(id)[0]

    def active_web(self,article_metadata_only=False):
        home="https://acme.example"
        pages={
          home:source(home,"# Acme\nA business software company",links=[home+"/blog",home+"/changelog",home+"/careers",home+"/signup","https://github.com/acme-fixture"]),
          home+"/blog":source(home+"/blog","# Blog\nCompany announcements",links=[home+"/blog/category/news",home+"/blog/privacy",home+"/blog/older",home+"/blog/newer"]),
          home+"/changelog":source(home+"/changelog","# Changelog\nProduct releases",links=[home+"/changelog/tag/api",home+"/changelog/new-api"]),
          home+"/careers":source(home+"/careers","# Careers\n2 open positions\nBackend engineer — Remote full time\nApply now"),
          home+"/signup":source(home+"/signup","# Create your account\nWork email\nPassword\nContinue"),
          "https://github.com/acme-fixture":source("https://github.com/acme-fixture","# Acme source repository\nNovember 11, 2026\nPublished commit"),
          home+"/blog/older":source(home+"/blog/older","# Acme product announcement\nSeptember 1, 2026\nWe shipped the first edition."),
          home+"/blog/newer":source(home+"/blog/newer","# Acme product update\nNovember 12, 2026\nWe shipped an improved dashboard."),
          home+"/changelog/new-api":source(home+"/changelog/new-api","# New API release\n2026-11-13\nWe released a faster endpoint."),
        }
        if article_metadata_only:
            pages[home+"/blog/older"]=source(home+"/blog/older","# Acme early article\nThe first edition.",published_date="2026-09-01T10:00:00Z")
            pages[home+"/blog/newer"]=source(home+"/blog/newer","# Acme product update\nWe shipped an improved dashboard.",published_date="2026-11-12T08:30:00Z")
            pages[home+"/changelog/new-api"]=source(home+"/changelog/new-api","# New API release\nWe released a faster endpoint.",published_date="2026-11-13T09:30:00Z")
        return FixtureWeb(pages)

    def test_homepage_indexes_articles_and_operational_signals_persist_verdict(self):
        id,row=self.audit()
        web=self.active_web()
        Engine(self.store).fast_row(id,row,web,threading.Event())
        saved=self.store.rows(id)[0]
        self.assertEqual(saved["status"],"done")
        self.assertEqual(saved["result"]["verdict"],"alive")
        self.assertEqual(saved["result"]["latest_activity_date"],"2026-11-13")
        self.assertEqual(saved["result"]["signals_checked"],5)
        self.assertEqual(saved["result"]["signals_verified"],5)
        self.assertEqual(saved["original"],row["original"])
        self.assertEqual(saved["result"]["signals"]["blog"]["url"],"https://acme.example/blog/newer")
        self.assertEqual(saved["result"]["signals"]["release"]["url"],"https://acme.example/changelog/new-api")
        requested={url for call in web.fetch_calls for url in call}
        self.assertIn("https://acme.example/blog/newer",requested)
        self.assertIn("https://acme.example/changelog/new-api",requested)
        self.assertNotIn("https://acme.example/blog/category/news",requested)
        self.assertNotIn("https://acme.example/blog/privacy",requested)
        self.assertEqual(web.search_calls,[])
        for kind in SIGNALS:
            self.assertTrue(saved["result"]["signals"][kind]["checked_at"])
        self.assertIsNotNone(self.store.snapshot(id,"https://acme.example/blog/newer"))

    def unavailable_web(self,error_code="page_not_found",status=404):
        home="https://acme.example"
        reference="https://www.ycombinator.com/companies/acme"
        other="https://www.ycombinator.com/companies/otherco"
        errors={url:{"error":error_code,"status":status} for url in (home,home+"/blog",home+"/changelog",home+"/careers",home+"/signup")}
        pages={reference:source(reference,"# Acme\nStatus: Inactive\nWebsite: https://acme.example",title="Acme | Y Combinator"),
               other:source(other,"# OtherCo\nStatus: Inactive\nAcme used similar technology",title="OtherCo | Y Combinator")}
        return FixtureWeb(pages,errors,[{"url":other,"snippet":"Acme shut down"}]),reference

    def test_terminal_homepage_search_and_exact_input_reference_persist_corroboration(self):
        web,reference=self.unavailable_web()
        id,row=self.audit(reference=reference)
        Engine(self.store).fast_row(id,row,web,threading.Event())
        saved=self.store.rows(id)[0]
        self.assertEqual(saved["status"],"done")
        self.assertEqual(saved["result"]["verdict"],"zombie")
        self.assertEqual(saved["result"]["closure"]["url"],reference)
        self.assertIn(reference,saved["result"]["evidence_links"])
        self.assertEqual(saved["result"]["signals_checked"],5)
        self.assertTrue(web.search_calls)
        self.assertEqual(saved["original"],row["original"])

    def test_temporary_homepage_failure_with_inactive_reference_remains_review(self):
        web,reference=self.unavailable_web("timeout",None)
        id,row=self.audit(reference=reference)
        Engine(self.store).fast_row(id,row,web,threading.Event())
        saved=self.store.rows(id)[0]
        self.assertEqual(saved["status"],"review")
        self.assertNotEqual(saved["result"]["verdict"],"zombie")
        self.assertTrue(saved["result"]["review_required"])

    def test_saved_pipeline_sources_survive_new_engine_without_refetch(self):
        id,row=self.audit()
        web=self.active_web()
        Engine(self.store).fast_row(id,row,web,threading.Event())
        original_result=self.store.rows(id)[0]["result"]
        web.fetch_calls=[]
        Engine(self.store).fast_row(id,self.store.rows(id)[0],web,threading.Event())
        self.assertEqual(web.fetch_calls,[])
        self.assertEqual(self.store.rows(id)[0]["result"]["latest_activity_date"],original_result["latest_activity_date"])

    def test_exact_article_publication_metadata_fills_missing_visible_date(self):
        id,row=self.audit()
        web=self.active_web(article_metadata_only=True)
        Engine(self.store).fast_row(id,row,web,threading.Event())
        saved=self.store.rows(id)[0]
        self.assertEqual(saved["result"]["latest_activity_date"],"2026-11-13")
        self.assertEqual(saved["result"]["signals"]["release"]["latest_date"],"2026-11-13")
        self.assertTrue(saved["result"]["signals"]["release"]["date_verified"])
        self.assertEqual(saved["result"]["signals"]["release"]["date_source"],"page_metadata")

    def test_future_partial_and_invalid_publication_metadata_are_rejected(self):
        for value in ("2050-01-01T12:00:00Z","2026-11","not a date"):
            with self.subTest(published_date=value):
                url="https://acme.example/blog/new-article"
                observed=observe_page("blog",url,source(url,"# Acme product update\nAn improved dashboard.",published_date=value),
                                      linked=True,company_url="https://acme.example")
                self.assertIsNone(observed["latest_date"])
                self.assertFalse(observed["date_verified"])

    def test_publication_metadata_does_not_turn_policy_page_into_product_activity(self):
        url="https://acme.example/privacy"
        observed=observe_page("blog",url,source(url,"# Privacy Policy\nEffective date: November 10, 2026\nOur legal terms.",published_date="2026-11-10T12:00:00Z"),
                              linked=True,company_url="https://acme.example")
        self.assertIsNone(observed["latest_date"])
        self.assertFalse(observed["date_verified"])


if __name__=="__main__":unittest.main()
