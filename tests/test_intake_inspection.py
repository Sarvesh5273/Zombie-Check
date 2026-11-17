"""Bounded intake-inspection lifecycle with fake transports and temporary DBs."""
import copy
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from zombiecheck.engine import Engine
from zombiecheck.ingest import parse_csv,map_rows
from zombiecheck.inspect import inspect_intake
from zombiecheck.models import utcnow
from zombiecheck.store import Store
from zombiecheck.tinyfish import TinyFish,APIError
from tests.test_core import csv_text

URL="https://job-boards.greenhouse.io/acme/jobs/101"


class InspectionClient:
    def __init__(self):
        self.queue_calls=[]
        self.run_calls=[]
        self.browser_calls=[]
        self.run_id=str(uuid.uuid4())
        self.queue_error=None
        self.run_status="COMPLETED"
        self.observation={"final_url":URL,"posting_id":"101","title":"Engineer 101",
            "application_form_visible":True,"application_fields":[{"label":"First Name","type":"input_text"}]}

    def queue_intake_inspection(self,url,title,posting_id):
        self.queue_calls.append((url,title,posting_id))
        if self.queue_error:raise self.queue_error
        return {"run_id":self.run_id}

    def agent_run(self,run_id):
        self.run_calls.append(run_id)
        return {"status":self.run_status,"finished_at":utcnow(),"num_of_steps":3,
                "result":copy.deepcopy(self.observation),"error":None}

    def browser_signup(self,url):
        self.browser_calls.append(url)
        return {"verified":True,"final_url":self.observation["final_url"],"fields":[{"label":"First Name","type":"text"}]}


class IntakeInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))
        parsed=parse_csv(csv_text([["Engineer 101",URL]],("title","job_url")))
        self.id=self.store.create_audit(parsed,map_rows(parsed,0,1),"Intake fixture",{"budget":1,"request_budget":1,"mode":"jobs"})
        self.result={"identity":{"verified":True,"status":"same","canonical_url":URL},"employer_name":"Acme",
                     "current_job_title":"Engineer 101","signals":{"signup":{"kind":"signup","url":URL,"status":"unknown","verified":False}}}
        self.store.row_update(self.id,"R000001",status="done",raw={"posting_id":"101"},result=self.result)
        self.client=InspectionClient()
        self.engine=Engine(self.store,client_factory=lambda _:self.client)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def state(self):
        return self.store.rows(self.id)[0]["result"].get("intake_inspections",{}).get("agent",{})

    def test_existing_run_reattaches_without_new_paid_queue_or_reservation(self):
        self.result["intake_inspections"]={"agent":{"status":"running","run_id":self.client.run_id,"reserved_usd":0.096}}
        self.store.row_update(self.id,"R000001",result=self.result)
        self.store.reserve_request(self.id,0.096)
        state=inspect_intake(self.engine,self.id,"R000001",method="agent")
        self.assertTrue(state["verified"])
        self.assertEqual(self.client.queue_calls,[])
        self.assertEqual(self.client.run_calls,[self.client.run_id])
        self.assertAlmostEqual(self.store.audit(self.id)["api_reserved"],0.096)

    def test_completed_inspection_is_reused_without_requeue(self):
        first=inspect_intake(self.engine,self.id,"R000001",method="agent")
        second=inspect_intake(self.engine,self.id,"R000001",method="agent")
        self.assertTrue(first["verified"])
        self.assertEqual(second["run_id"],first["run_id"])
        self.assertEqual(len(self.client.queue_calls),1)
        self.assertEqual(len(self.client.run_calls),1)

    def test_agent_posting_id_and_final_route_must_both_match(self):
        for change in ({"posting_id":"999"},{"final_url":"https://job-boards.greenhouse.io/acme/jobs/999"},
                       {"final_url":"https://unrelated.example/jobs/101"}):
            with self.subTest(change=change):
                self.store.row_update(self.id,"R000001",result=copy.deepcopy(self.result))
                self.client.observation.update(final_url=URL,posting_id="101")
                self.client.observation.update(change)
                state=inspect_intake(self.engine,self.id,"R000001",method="agent")
                self.assertFalse(state["verified"])
                self.assertFalse(self.store.rows(self.id)[0]["result"]["signals"]["signup"]["verified"])

    def test_browser_unrelated_final_route_is_not_verified(self):
        self.client.observation["final_url"]="https://unrelated.example/jobs/101"
        state=inspect_intake(self.engine,self.id,"R000001",method="browser")
        self.assertFalse(state["verified"])
        self.assertFalse(self.store.rows(self.id)[0]["result"]["signals"]["signup"]["verified"])

    def test_uncertain_paid_queue_outcome_never_queues_duplicate(self):
        self.client.queue_error=APIError(0,"Connection lost after queue",ambiguous=True)
        with self.assertRaises(APIError):inspect_intake(self.engine,self.id,"R000001",method="agent")
        self.assertEqual(self.state()["status"],"uncertain")
        with self.assertRaises(ValueError):inspect_intake(self.engine,self.id,"R000001",method="agent")
        self.assertEqual(len(self.client.queue_calls),1)
        self.assertAlmostEqual(self.store.audit(self.id)["api_reserved"],0.096)

    def test_supplied_run_id_resolves_uncertain_outcome_without_new_queue(self):
        self.result["intake_inspections"]={"agent":{"status":"uncertain","reserved_usd":0.096}}
        self.store.row_update(self.id,"R000001",result=self.result)
        state=inspect_intake(self.engine,self.id,"R000001",method="agent",run_id=self.client.run_id)
        self.assertTrue(state["verified"])
        self.assertEqual(self.client.queue_calls,[])
        self.assertEqual(self.client.run_calls,[self.client.run_id])

    def test_unverified_original_identity_cannot_start_inspection(self):
        self.result["identity"]["verified"]=False
        self.store.row_update(self.id,"R000001",result=self.result)
        with self.assertRaises(ValueError):inspect_intake(self.engine,self.id,"R000001",method="agent")
        self.assertEqual(self.client.queue_calls,[])
        self.assertEqual(self.client.browser_calls,[])

    def test_live_owner_refuses_inspection_without_spend_or_lease_changes(self):
        owner_token=str(uuid.uuid4())
        self.assertTrue(self.store.claim_worker(self.id,owner_token,os.getpid()))
        self.assertTrue(self.store.reserve_request(self.id,0.25))
        owner_before=self.store.query("SELECT * FROM workers WHERE audit_id=?",(self.id,))
        reservation_before=self.store.audit(self.id)["api_reserved"]
        row_before=copy.deepcopy(self.store.rows(self.id)[0])

        for method in ("agent","browser"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError,"Another worker owns this audit"):
                    inspect_intake(self.engine,self.id,"R000001",method=method)
                self.assertEqual(self.client.queue_calls,[])
                self.assertEqual(self.client.run_calls,[])
                self.assertEqual(self.client.browser_calls,[])
                self.assertEqual(self.store.audit(self.id)["api_reserved"],reservation_before)
                self.assertEqual(self.store.query("SELECT * FROM workers WHERE audit_id=?",(self.id,)),owner_before)
                self.assertEqual(self.store.rows(self.id)[0],row_before)

    def test_tinyfish_queue_enforces_six_steps_and_duration_cap(self):
        client=TinyFish(key="fixture-key")
        requests=[]
        def request(method,url,body=None,**kw):
            requests.append((method,url,body,kw))
            return {"run_id":str(uuid.uuid4())}
        client.request=request
        client.queue_intake_inspection(URL,"Engineer 101","101")
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0][2]["agent_config"]["max_steps"],6)
        self.assertEqual(requests[0][2]["agent_config"]["max_duration_seconds"],60)
        self.assertIn("Do not fill, submit",requests[0][2]["goal"])

    def test_403_never_silently_retries_without_caps_and_reservation_is_refunded(self):
        client=TinyFish(key="fixture-key")
        requests=[]
        def request(method,url,body=None,**kw):
            requests.append((method,url,body,kw))
            raise APIError(403,"Step caps require beta",ambiguous=False)
        client.request=request
        engine=Engine(self.store,client_factory=lambda _:client)
        with self.assertRaises(APIError) as raised:inspect_intake(engine,self.id,"R000001",method="agent")
        self.assertEqual(raised.exception.status,403)
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0][2]["agent_config"]["max_steps"],6)
        self.assertEqual(self.state()["status"],"failed")
        self.assertAlmostEqual(self.store.audit(self.id)["api_reserved"],0)


if __name__=="__main__":unittest.main()
