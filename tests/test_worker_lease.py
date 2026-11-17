"""Cross-engine coordination tests using fake work and temporary databases only."""
import contextlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from zombiecheck.engine import Engine
from zombiecheck.ingest import map_rows, parse_csv
from zombiecheck.store import Store
from tests.test_core import csv_text, result_fixture


class WorkerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp.name)/"fixture.sqlite3")
        self.owner_store = Store(self.db_path)
        self.control_store = Store(self.db_path)
        parsed = parse_csv(csv_text([["Fixture Company", "https://fixture.example", ""]]))
        self.audit_id = self.owner_store.create_audit(parsed,map_rows(parsed,0,1),"Worker lease fixture",{"budget":0,"strategy":"triage"})
        self.owner = Engine(self.owner_store,client_factory=lambda _: object())
        self.control = Engine(self.control_store,client_factory=lambda _: object())
        self.unblock = threading.Event()
        self.engines = [self.owner,self.control]

    def tearDown(self):
        self.unblock.set()
        for engine in self.engines:
            for stop in engine.stops.values(): stop.set()
            for thread in engine.threads.values(): thread.join(timeout=2)
        self.control_store.db.close()
        self.owner_store.db.close()
        self.temp.cleanup()

    def held_work(self,entered,stop_seen=None):
        def work(audit_id,row,client,stop,raw=None):
            entered.set()
            for _ in range(200):
                if stop.is_set():
                    if stop_seen: stop_seen.set()
                    return
                if self.unblock.wait(0.01):
                    return
        return work

    def test_second_engine_cannot_start_same_active_audit(self):
        first_entered,second_entered=threading.Event(),threading.Event()
        self.owner.fast_row=self.held_work(first_entered)
        self.control.fast_row=self.held_work(second_entered)
        self.owner.start(self.audit_id)
        self.assertTrue(first_entered.wait(1),"Owner worker did not start")
        try:
            self.control.start(self.audit_id)
        except (RuntimeError,ValueError):
            # Explicit refusal is allowed; no second worker may run.
            pass
        self.assertFalse(second_entered.wait(0.15),"A second Engine entered work for an already-owned audit")
        self.assertEqual(self.owner_store.audit(self.audit_id)["status"],"running")

    def test_pause_from_other_engine_is_observed_by_owner(self):
        entered,stop_seen=threading.Event(),threading.Event()
        self.owner.fast_row=self.held_work(entered,stop_seen)
        self.owner.start(self.audit_id)
        self.assertTrue(entered.wait(1),"Owner worker did not start")
        self.control.pause(self.audit_id)
        self.assertTrue(stop_seen.wait(2.5),"Persisted pause was not observed by the owning Engine")
        self.owner.threads[self.audit_id].join(timeout=1)
        self.assertFalse(self.owner.threads[self.audit_id].is_alive())
        self.assertEqual(self.owner_store.audit(self.audit_id)["status"],"paused")

    def test_engine_start_recovers_expired_owner_lease(self):
        self.assertTrue(self.owner_store.claim_worker(self.audit_id,"expired-owner",os.getpid()))
        self.owner_store.execute("UPDATE workers SET heartbeat=? WHERE audit_id=?",(time.time()-121,self.audit_id))
        entered=threading.Event()
        self.control.fast_row=self.held_work(entered)
        self.control.start(self.audit_id)
        self.assertTrue(entered.wait(1),"A stale saved lease prevented recovery")
        owner=self.owner_store.query("SELECT token FROM workers WHERE audit_id=?",(self.audit_id,))
        self.assertEqual(len(owner),1)
        self.assertNotEqual(owner[0]["token"],"expired-owner")


class WorkerStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        path=str(Path(self.temp.name)/"fixture.sqlite3")
        self.first,self.second=Store(path),Store(path)
        parsed=parse_csv(csv_text([["Fixture Company","https://fixture.example",""]]))
        self.audit_id=self.first.create_audit(parsed,map_rows(parsed,0,1),"Worker storage fixture",{"budget":0})

    def tearDown(self):
        self.second.db.close()
        self.first.db.close()
        self.temp.cleanup()

    def test_atomic_claim_across_independent_connections(self):
        barrier=threading.Barrier(2)
        claims=[]
        def claim(store,token):
            barrier.wait()
            claims.append(store.claim_worker(self.audit_id,token,os.getpid()))
        threads=[threading.Thread(target=claim,args=(self.first,"first")),
                 threading.Thread(target=claim,args=(self.second,"second"))]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=2)
        self.assertEqual(sorted(claims),[False,True])
        self.assertEqual(len(self.first.query("SELECT * FROM workers WHERE audit_id=?",(self.audit_id,))),1)

    def test_expired_owner_can_be_replaced_and_old_token_is_fenced(self):
        self.assertTrue(self.first.claim_worker(self.audit_id,"old-owner",os.getpid()))
        self.first.execute("UPDATE workers SET heartbeat=? WHERE audit_id=?",(time.time()-121,self.audit_id))
        self.assertTrue(self.second.claim_worker(self.audit_id,"replacement",os.getpid()))
        self.assertFalse(self.first.heartbeat_worker(self.audit_id,"old-owner"))
        self.assertFalse(self.first.release_worker(self.audit_id,"old-owner"))
        self.assertEqual(self.second.query("SELECT token FROM workers WHERE audit_id=?",(self.audit_id,))[0]["token"],"replacement")
        self.assertTrue(self.second.heartbeat_worker(self.audit_id,"replacement"))
        self.assertTrue(self.second.release_worker(self.audit_id,"replacement"))

    def test_dead_owner_recovered_even_with_fresh_heartbeat(self):
        self.assertTrue(self.first.claim_worker(self.audit_id,"dead-owner",os.getpid()))
        with patch.object(Store,"_pid_alive",return_value=False):
            self.assertTrue(self.second.claim_worker(self.audit_id,"replacement",os.getpid()))

    def test_lease_rejects_unknown_audit_and_invalid_ttl(self):
        with self.assertRaises(KeyError):self.first.claim_worker("missing","token",os.getpid())
        with self.assertRaises(ValueError):self.first.claim_worker(self.audit_id,"token",os.getpid(),ttl=0)
        with self.assertRaises(ValueError):self.first.claim_worker(self.audit_id,"token",os.getpid(),ttl=float("nan"))


class FullBudgetAdmissionTests(unittest.TestCase):
    """Exercise the actual HTTP handler without opening a server or running work."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def post_import(self,rows,budget):
        from zombiecheck import server
        capture={}
        class CapturedServer:
            def __init__(self,address,handler): capture["handler"]=handler
            def serve_forever(self): return
        with contextlib.redirect_stdout(io.StringIO()), patch.object(server,"Store",return_value=self.store), patch.object(server,"ThreadingHTTPServer",CapturedServer):
            server.serve("127.0.0.1",0)
        handler=object.__new__(capture["handler"])
        handler.path="/api/audits"
        handler.authorized=lambda:True
        handler.body=lambda:{"csv":csv_text(rows),"name":"Full budget admission fixture","strategy":"full","budget":budget,"name_column":0,"url_column":1}
        responses=[]
        handler.response=lambda value,status=200,**kwargs:responses.append((status,value))
        handler.do_POST()
        return responses[-1]

    def test_full_mode_admission_prices_unique_companies_not_duplicate_rows(self):
        rows=[["Fixture Company","https://fixture.example",str(i)] for i in range(500)]
        status,body=self.post_import(rows,0.10)
        self.assertEqual(status,201,body)
        self.assertEqual(body["total"],500)
        self.assertEqual(self.store.audit(body["id"])["budget"],0.10)

    def test_full_mode_rejects_budget_below_unique_company_cost(self):
        rows=[["Alpha","https://alpha.example",""],["Beta","https://beta.example",""]]
        status,body=self.post_import(rows,0.10)
        self.assertEqual(status,400,body)
        self.assertTrue(body["error"])
        self.assertEqual(self.store.query("SELECT COUNT(*) AS n FROM audits")[0]["n"],0)


if __name__=="__main__":unittest.main()
