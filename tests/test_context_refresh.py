"""Bounded employer source enrichment preserves independently checked roles."""
import copy
import datetime as dt
import json
import tempfile
import threading
import unittest
from pathlib import Path

from zombiecheck.engine import Engine
from zombiecheck.evidence import observe_page
from zombiecheck.ingest import parse_csv,map_rows
from zombiecheck.jobs import _drill_linked_source,refresh_job_context,run_jobs
from zombiecheck.store import Store
from tests.test_core import csv_text
from tests.test_jobs import JobFixtureClient,HOME,FIELDS,STAMP,source


class SharedContextRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def audit(self,client):
        parsed=parse_csv(csv_text([client.row(i) for i in client.ids],FIELDS))
        id=self.store.create_audit(parsed,map_rows(parsed,1,2),"Context fixture",{"mode":"jobs","budget":1,"strategy":"triage"})
        return id,Engine(self.store,client_factory=lambda _:client)

    def test_drill_uses_at_most_three_owned_actual_links_without_nav_or_duplicates(self):
        client=JobFixtureClient()
        id,engine=self.audit(client)
        index_url=HOME+"/blog"
        allowed=[HOME+"/blog/article-"+str(i) for i in range(1,5)]
        rejected=[HOME+"/blog/tags/news",HOME+"/blog/topics/ai",HOME+"/blog/search?q=x",
                  HOME+"/blog/engineering",HOME+"/privacy","https://unrelated.example/blog/post"]
        for url in allowed[:3]:client.pages[url]=source(url,"# An article\nNo dated activity established.")
        client.pages[allowed[3]]=source(allowed[3],"# Article\nNovember 16, 2026")
        index=source(index_url,"# Blog\nCompany updates",rejected+[allowed[0],allowed[0]+"?utm_source=newsletter"]+allowed[1:])
        signal=observe_page("blog",index_url,page=index,company_url=HOME)
        observed=_drill_linked_source(engine,id,client,"blog",HOME,{"page":index},signal,set(),threading.Event())
        checked=[u for call in client.fetch_calls for u in call]
        self.assertEqual(checked,allowed[:3])
        self.assertEqual(len(observed["drill_checks"]),3)
        self.assertIsNone(observed["latest_date"])
        self.assertEqual(client.creates,[])

    def test_drill_accepts_metadata_date_on_an_actual_linked_article(self):
        client=JobFixtureClient()
        id,engine=self.audit(client)
        index_url=HOME+"/blog"
        first,second=HOME+"/blog/undated",HOME+"/blog/new-feature"
        client.pages[first]=source(first,"# Article\nNo publication date")
        client.pages[second]=source(second,"# New feature\nExample log 2026-10-29T12:00:00Z")
        client.pages[second]["published_date"]="2026-11-16T05:30:00Z"
        index=source(index_url,"# Blog\nLatest articles",[first,second])
        signal=observe_page("blog",index_url,page=index,company_url=HOME)
        observed=_drill_linked_source(engine,id,client,"blog",HOME,{"page":index},signal,set(),threading.Event())
        self.assertEqual(observed["url"],second)
        self.assertEqual(observed["latest_date"],"2026-11-16")
        self.assertEqual(observed["source_index_url"],index_url)
        self.assertEqual([d["url"] for d in observed["drill_checks"]],[first,second])

    @staticmethod
    def core(row):
        result=row["result"]
        data={k:copy.deepcopy(v) for k,v in result.items() if k not in ("signals","signals_checked","signals_verified","evidence_links")}
        data["job_signals"]={k:copy.deepcopy(result["signals"][k]) for k in ("jobs","signup")}
        data["original_row"]={k:copy.deepcopy(row[k]) for k in ("original","raw","dataset_id","status")}
        return data

    def test_refresh_repairs_cached_shared_date_without_new_dataset_or_role_changes(self):
        client=JobFixtureClient((101,102),first_days=121)
        for posting_id in client.ids:client.role_change(posting_id,updated_at=(STAMP-dt.timedelta(days=20)).isoformat())
        client.pages[HOME+"/blog"]=source(HOME+"/blog","# New product feature\nExample log 2026-10-29T12:00:00Z")
        client.pages[HOME+"/blog"]["published_date"]="2026-11-16T05:30:00Z"
        id,engine=self.audit(client)
        run_jobs(engine,id,threading.Event())
        # Simulate the saved pre-fix interpretation of an already-fetched source.
        config=self.store.audit(id)["config"]
        for saved in config["jobs_state"]["employers"].values():
            saved["raw"]["blog"]=HOME+"/incorrect-tinyset-url"
            saved["signals"]["blog"].update(latest_date="2026-11-17",discovered_by="tinysearch",discovery_query="Acme official blog")
        self.store.execute("UPDATE audits SET config=? WHERE id=?",(json.dumps(config),id))
        for row in self.store.rows(id):
            result=row["result"]
            result["signals"]["blog"].update(latest_date="2026-11-17",discovered_by="tinysearch",discovery_query="Acme official blog")
            result["intake_inspections"]={"agent":{"status":"complete","verified":True,"run_id":"fixture-existing-inspection"}}
            self.store.row_update(id,row["row_id"],result=result)
        before={r["row_id"]:self.core(r) for r in self.store.rows(id)}
        creates=len(client.creates)
        calls=len(client.fetch_calls)
        searches=len(client.search_calls)
        summary=refresh_job_context(engine,id)
        self.assertTrue(summary["job_core_unchanged"])
        self.assertEqual(summary["rows_enhanced"],2)
        self.assertEqual(len(client.creates),creates)
        self.assertEqual(len(client.search_calls),searches)
        requested=[u for call in client.fetch_calls[calls:] for u in call]
        for posting_id in client.ids:
            self.assertNotIn(client.role_url(posting_id),requested)
            self.assertNotIn(client.job_url(posting_id),requested)
        for row in self.store.rows(id):
            self.assertEqual(self.core(row),before[row["row_id"]])
            self.assertEqual(row["result"]["signals"]["blog"]["latest_date"],"2026-11-16")
            self.assertEqual(row["result"]["signals"]["blog"]["discovered_by"],"tinysearch")

    def test_refresh_without_matched_employer_context_does_not_create_dataset(self):
        client=JobFixtureClient()
        id,engine=self.audit(client)
        with self.assertRaises(ValueError):refresh_job_context(engine,id)
        self.assertEqual(client.creates,[])
        self.assertEqual(client.fetch_calls,[])


if __name__=="__main__":unittest.main()
