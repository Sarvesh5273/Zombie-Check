"""Offline regressions for identity mistakes found by the real audit council.

Text fixtures reproduce the failure shapes. They are not asserted to be live
copies of the named sites, and this test module makes no network requests.
"""
import tempfile
import threading
import unittest
from pathlib import Path

from zombiecheck.evidence import apply_identity_evidence, identity_from_page, closure_quote
from zombiecheck.ingest import parse_csv,map_rows
from zombiecheck.store import Store
from tests.test_core import csv_text


def source(url,text,title=None,links=()):
    return {"url":url,"final_url":url,"text":text,"title":title,"links":list(links)}


class CouncilIdentityRegressions(unittest.TestCase):
    def test_sapling_wordpress_blog_shutdown_is_not_company_shutdown(self):
        passage="We permanently shut down blog.sapling.ai, our WordPress blog."
        for name in ("Sapling","Sapling.ai"):
            with self.subTest(name=name):
                row={"name":name,"website":"https://sapling.ai"}
                homepage=source(row["website"],"Sapling writing assistant.\nCreate your account and improve your writing.")
                identity=identity_from_page(row,homepage)
                article=source("https://security-review.example/sapling",passage,links=[row["website"]])
                self.assertIsNone(apply_identity_evidence(row,identity,article))
                self.assertEqual(identity["status"],"same")
                self.assertTrue(identity["verified"])
                self.assertEqual(identity_from_page(row,source(row["website"],"Sapling writing assistant.\n"+passage))["status"],"same")

    def test_domain_url_mention_is_not_a_named_company_closure_subject(self):
        self.assertEqual(closure_quote("Sapling","We shut down https://sapling.ai/an-endpoint."),"")

    def test_whole_company_closures_survive_component_guard(self):
        fixtures=(("Comradery","Unfortunately, Comradery is no longer running"),
                  ("Penguin","Penguin has ceased operations."))
        for name,passage in fixtures:
            with self.subTest(name=name):
                row={"name":name,"website":"https://"+name.casefold()+".example"}
                observed=identity_from_page(row,source(row["website"],passage))
                self.assertEqual(observed["status"],"closed")
                self.assertTrue(observed["verified"])
                self.assertIn(passage,observed["quote"])

    def test_avalanche_studios_article_cannot_close_unrelated_avalanche(self):
        row={"name":"Avalanche","website":"https://useavalanche.com"}
        identity={"status":"unknown","verified":False,"canonical_url":row["website"]}
        article=source("https://gaming-news.example/avalanche-studios",
                       "Avalanche Studios has shut down operations.\nThe game developer's history.",
                       title="Avalanche Studios closes",links=["https://avalanchestudios.example"])
        closure=apply_identity_evidence(row,identity,article)
        self.assertIsNone(closure)
        self.assertNotEqual(identity["status"],"closed")
        self.assertFalse(identity["verified"])

    def test_office_or_studio_closure_is_not_whole_company_closure(self):
        row={"name":"Acme","website":"https://acme.example"}
        for passage in ("Acme has shut down its London office; the business continues.",
                        "Acme has shut down its recording studio; other products remain available."):
            with self.subTest(passage=passage):
                identity={"status":"same","verified":True,"canonical_url":row["website"]}
                closure=apply_identity_evidence(row,identity,source(row["website"],passage))
                self.assertIsNone(closure)
                self.assertEqual(identity["status"],"same")

    def test_comradery_no_longer_running_on_original_homepage_is_closure(self):
        row={"name":"Comradery","website":"https://comradery.example"}
        observed=identity_from_page(row,source(row["website"],"Comradery is no longer running. Thank you for being part of the community."))
        self.assertEqual(observed["status"],"closed")
        self.assertTrue(observed["verified"])
        self.assertIn("no longer running",observed["quote"])

    def test_named_original_domain_for_sale_title_is_parking(self):
        row={"name":"Acme","website":"https://acme.example"}
        observed=identity_from_page(row,source(row["website"],"Premium domain listing. Contact the seller.",
                                              title="acme.example is for sale"))
        self.assertEqual(observed["status"],"parked")
        self.assertTrue(observed["verified"])

    def test_portfolio_acquire_wording_does_not_establish_acquisition_of_subject(self):
        row={"name":"Acme","website":"https://acme.example"}
        identity={"status":"same","verified":True,"canonical_url":row["website"]}
        portfolio=source("https://fund.example/portfolio",
            "# Portfolio\nAcme — https://acme.example\nWe acquire outstanding companies and support their founders.",
            links=[row["website"]])
        closure=apply_identity_evidence(row,identity,portfolio)
        self.assertIsNone(closure)
        self.assertEqual(identity["status"],"same")

    def test_external_named_closure_needs_original_host_identity(self):
        row={"name":"Acme","website":"https://acme.example"}
        identity={"status":"unknown","verified":False,"canonical_url":row["website"]}
        closure=apply_identity_evidence(row,identity,source("https://news.example/acme","Acme has shut down its business."))
        self.assertIsNone(closure)
        self.assertFalse(identity["verified"])

    def test_external_closure_with_original_host_mention_or_link_is_supported(self):
        row={"name":"Acme","website":"https://acme.example"}
        for text,links in (("Acme has shut down its business. Its website was acme.example.",()),
                           ("Acme has shut down its business.",(row["website"],))):
            with self.subTest(text=text,links=links):
                identity={"status":"unknown","verified":False,"canonical_url":row["website"]}
                closure=apply_identity_evidence(row,identity,source("https://news.example/acme",text,links=links))
                self.assertIsNotNone(closure)
                self.assertTrue(closure["verified"])

    def test_scoped_named_acquisition_keeps_original_product_continuity(self):
        row={"name":"Acme","website":"https://acme.example"}
        identity={"status":"same","verified":True,"canonical_url":row["website"]}
        article=source("https://parent.example/news/acme",
                       "Acme was acquired by ParentCo. Original product remains available.",links=[row["website"]])
        closure=apply_identity_evidence(row,identity,article)
        self.assertIsNone(closure)
        self.assertEqual(identity["status"],"acquired_operating")
        self.assertTrue(identity["verified"])


class CombinedCostReservationRegression(unittest.TestCase):
    def test_api_upper_bound_and_existing_research_reservations_share_atomic_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(str(Path(temp)/"fixture.sqlite3"))
            try:
                parsed=parse_csv(csv_text([["Acme","https://acme.example",""]]))
                id=store.create_audit(parsed,map_rows(parsed,0,1),"Cost fixture",{"budget":1,"request_budget":1,"strategy":"triage"})
                self.assertTrue(store.reserve(id,0.40))
                barrier=threading.Barrier(4)
                results=[]
                def reserve_request():
                    barrier.wait()
                    results.append(store.reserve_request(id,0.30))
                threads=[threading.Thread(target=reserve_request) for _ in range(4)]
                for thread in threads:thread.start()
                for thread in threads:thread.join(timeout=2)
                self.assertEqual(sum(results),2)
                audit=store.audit(id)
                self.assertAlmostEqual(audit["reserved"],0.40)
                self.assertAlmostEqual(audit["api_reserved"],0.60)
                self.assertLessEqual(audit["reserved"]+audit["api_reserved"],1+1e-8)
                self.assertFalse(store.reserve_request(id,0.01))
            finally:
                store.db.close()


if __name__=="__main__":unittest.main()
