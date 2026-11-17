"""Mapped job import and safe identity derivation; synthetic no-network fixtures."""
import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from zombiecheck.engine import Engine
from zombiecheck.ingest import parse_csv,map_rows,job_column_mapping
from zombiecheck.jobs import _read_fields
from zombiecheck.store import Store
from tests.test_core import csv_text
from tests.test_jobs import JobFixtureClient,HOME,BASE,FEED

HEADERS=("Employer label","Role heading","Posting link","Employer home","Reviewer note")
MAPPING={"employer":"Employer label","title":"Role heading","job_url":"Posting link","employer_website":"Employer home"}


class GenericJobImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def create(self,modern=False,extra=None,index_mapping=False):
        headers=list(HEADERS)
        row=["Acme","Engineer 101",JobFixtureClient.job_url(101,modern),HOME,"Keep exactly"]
        mapping=dict(MAPPING)
        if extra:
            for field,value in extra.items():
                label="Custom "+field
                headers.append(label)
                row.append(value)
                mapping[field]=label
        if index_mapping:mapping={field:headers.index(label) for field,label in mapping.items()}
        parsed=parse_csv(csv_text([row],headers))
        id=self.store.create_audit(parsed,map_rows(parsed,1,2),"Mapped job fixture",
            {"budget":1,"strategy":"triage","mode":"jobs","job_columns":mapping})
        return id,self.store.rows(id)[0],row

    def test_nonstandard_name_mappings_derive_exact_greenhouse_identity(self):
        for modern in (False,True):
            with self.subTest(modern=modern):
                id,row,original=self.create(modern)
                values=_read_fields(self.store.audit(id),row)
                self.assertEqual(values["employer"],"Acme")
                self.assertEqual(values["title"],"Engineer 101")
                self.assertEqual(values["token"],"acme")
                self.assertEqual(values["posting_id"],"101")
                self.assertEqual(values["job_api_url"],BASE+"/jobs/101?questions=true")
                self.assertEqual(values["source_url"],FEED)
                self.assertEqual(self.store.rows(id)[0]["original"],original)

    def test_zero_based_index_mappings_include_first_column(self):
        id,row,_=self.create(index_mapping=True)
        values=_read_fields(self.store.audit(id),row)
        self.assertEqual(values["employer"],"Acme")
        self.assertEqual(values["posting_id"],"101")

    def test_invalid_mapping_field_heading_boolean_or_index_is_rejected(self):
        for mapping in ({"unknown_field":0},{"employer":"Heading not present"},
                        {"employer":True},{"employer":-1},{"employer":len(HEADERS)}):
            with self.subTest(mapping=mapping):
                with self.assertRaises(ValueError):job_column_mapping(list(HEADERS),mapping)

    def test_standard_job_header_aliases_are_discovered(self):
        headers=["Company","Role","Job URL","Company Website"]
        mapping=job_column_mapping(headers)
        self.assertEqual(mapping["employer"],0)
        self.assertEqual(mapping["title"],1)
        self.assertEqual(mapping["job_url"],2)
        self.assertEqual(mapping["employer_website"],3)

    def test_conflicting_explicit_role_id_api_or_feed_token_is_rejected(self):
        cases=({"job_id":"999"},{"job_id":"greenhouse:other:101"},
               {"job_api_url":BASE+"/jobs/999?questions=true"},
               {"job_api_url":"https://boards-api.greenhouse.io/v1/boards/other/jobs/101?questions=true"},
               {"source_url":"https://boards-api.greenhouse.io/v1/boards/other/jobs?content=true"})
        for extra in cases:
            with self.subTest(extra=extra):
                id,row,_=self.create(extra=extra)
                with self.assertRaises(ValueError):_read_fields(self.store.audit(id),row)

    def test_unknown_custom_host_does_not_guess_board_token_from_employer_name(self):
        id,row,_=self.create()
        row["website"]="https://careers.example/roles/101"
        row["original"][2]=row["website"]
        with self.assertRaises(ValueError):_read_fields(self.store.audit(id),row)

    def test_actual_engine_dispatch_handles_mapped_derived_input(self):
        id,row,original=self.create(modern=True)
        client=JobFixtureClient()
        client.add_role(101,modern=True)
        Engine(self.store,client_factory=lambda _:client).run(id,threading.Event())
        saved=self.store.rows(id)[0]
        self.assertEqual(saved["status"],"done")
        self.assertEqual(saved["result"]["verdict"],"alive")
        self.assertEqual(saved["original"],original)
        self.assertEqual(len(client.creates),1)

    def test_server_retains_requested_job_field_mappings(self):
        from zombiecheck import server
        capture={}
        class NoHTTP:
            def __init__(self,address,handler):capture["handler"]=handler
            def serve_forever(self):pass
        with contextlib.redirect_stdout(io.StringIO()),patch.object(server,"Store",return_value=self.store),patch.object(server,"ThreadingHTTPServer",NoHTTP):
            server.serve("127.0.0.1",0)
        handler=object.__new__(capture["handler"])
        handler.path="/api/audits"
        handler.authorized=lambda:True
        row=["Acme","Engineer 101",JobFixtureClient.job_url(101),HOME,"Keep exactly"]
        handler.body=lambda:{"csv":csv_text([row],HEADERS),"mode":"jobs","name_column":1,"url_column":2,"budget":1,"job_columns":MAPPING}
        responses=[]
        handler.response=lambda value,status=200,**kw:responses.append((status,value))
        handler.do_POST()
        status,body=responses[-1]
        self.assertEqual(status,201,body)
        saved_mapping=self.store.audit(body["id"])["config"]["job_columns"]
        for field,label in MAPPING.items():
            selected=saved_mapping[field]
            self.assertEqual(HEADERS[selected] if isinstance(selected,int) else selected,label)
        values=_read_fields(self.store.audit(body["id"]),self.store.rows(body["id"])[0])
        self.assertEqual(values["posting_id"],"101")

    def test_cli_import_retains_nonstandard_mappings_for_derivation(self):
        from zombiecheck import __main__ as cli
        path=Path(self.temp.name)/"mapped.csv"
        path.write_text(csv_text([["Acme","Engineer 101",JobFixtureClient.job_url(101),HOME,"Keep exactly"]],HEADERS))
        stdout=io.StringIO()
        args=["zombiecheck","--db",str(Path(self.temp.name)/"fixture.sqlite3"),"import",str(path),
              "--mode","jobs","--name-column","Role heading","--url-column","Posting link",
              "--job-columns",json.dumps(MAPPING)]
        with patch.object(sys,"argv",args),patch.object(cli,"Store",return_value=self.store),contextlib.redirect_stdout(stdout):cli.main()
        imported=json.loads(stdout.getvalue())
        audit=self.store.audit(imported["audit_id"])
        values=_read_fields(audit,self.store.rows(audit["id"])[0])
        self.assertEqual(values["employer"],"Acme")
        self.assertEqual(values["posting_id"],"101")
        self.assertEqual(values["source_url"],FEED)


if __name__=="__main__":unittest.main()
