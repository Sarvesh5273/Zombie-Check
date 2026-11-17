"""Startup lease recovery with temporary DBs and no real HTTP/network worker."""
import contextlib
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from zombiecheck.ingest import parse_csv,map_rows
from zombiecheck.store import Store
from tests.test_core import csv_text,result_fixture


class StartupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"fixture.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def audit(self,status="running"):
        parsed=parse_csv(csv_text([["Acme","https://acme.example","original cell"]]))
        id=self.store.create_audit(parsed,map_rows(parsed,0,1),"Startup fixture",{"budget":0})
        self.store.set_status(id,status)
        return id

    def startup(self):
        from zombiecheck import server
        class NoHTTP:
            def __init__(self,address,handler):pass
            def serve_forever(self):pass
        with contextlib.redirect_stdout(io.StringIO()),patch.object(server,"Store",return_value=self.store),patch.object(server,"ThreadingHTTPServer",NoHTTP):
            server.serve("127.0.0.1",0)

    def test_server_startup_preserves_fresh_live_worker_audit(self):
        id=self.audit()
        self.assertTrue(self.store.claim_worker(id,"live-owner",os.getpid()))
        self.startup()
        self.assertEqual(self.store.audit(id)["status"],"running")
        self.assertEqual(self.store.query("SELECT token FROM workers WHERE audit_id=?",(id,))[0]["token"],"live-owner")

    def test_server_startup_preserves_pending_pause_for_live_owner(self):
        id=self.audit("pausing")
        self.assertTrue(self.store.claim_worker(id,"live-owner",os.getpid()))
        self.startup()
        self.assertEqual(self.store.audit(id)["status"],"pausing")

    def test_server_startup_pauses_interrupted_audit_without_owner(self):
        id=self.audit()
        self.store.row_update(id,"R000001",status="checking",result=result_fixture(),dataset_id="saved-remote")
        before=self.store.rows(id)[0]
        self.startup()
        after=self.store.rows(id)[0]
        self.assertEqual(self.store.audit(id)["status"],"paused")
        self.assertEqual(after["original"],before["original"])
        self.assertEqual(after["result"],before["result"])
        self.assertEqual(after["dataset_id"],"saved-remote")

    def test_server_startup_pauses_expired_owner_and_releases_stale_lease(self):
        id=self.audit()
        self.assertTrue(self.store.claim_worker(id,"expired-owner",os.getpid()))
        self.store.execute("UPDATE workers SET heartbeat=? WHERE audit_id=?",(time.time()-121,id))
        self.startup()
        self.assertEqual(self.store.audit(id)["status"],"paused")
        self.assertEqual(self.store.query("SELECT * FROM workers WHERE audit_id=?",(id,)),[])

    def test_server_startup_pauses_dead_owner_even_with_fresh_heartbeat(self):
        id=self.audit()
        self.assertTrue(self.store.claim_worker(id,"dead-owner",os.getpid()))
        with patch.object(Store,"_pid_alive",return_value=False):self.startup()
        self.assertEqual(self.store.audit(id)["status"],"paused")
        self.assertEqual(self.store.query("SELECT * FROM workers WHERE audit_id=?",(id,)),[])

    def test_unstarted_completed_and_review_audits_are_not_reclassified(self):
        ids={status:self.audit(status) for status in ("ready","complete","needs_review","paused","error")}
        self.startup()
        self.assertEqual({status:self.store.audit(id)["status"] for status,id in ids.items()},
                         {status:status for status in ids})

    def test_recovery_is_idempotent_and_leaves_healthy_owner_heartbeat_untouched(self):
        healthy=self.audit()
        orphan=self.audit()
        self.assertTrue(self.store.claim_worker(healthy,"live-owner",os.getpid()))
        heartbeat=self.store.query("SELECT heartbeat FROM workers WHERE audit_id=?",(healthy,))[0]["heartbeat"]
        self.store.recover_interrupted(ttl=120)
        self.store.recover_interrupted(ttl=120)
        self.assertEqual(self.store.audit(healthy)["status"],"running")
        self.assertEqual(self.store.audit(orphan)["status"],"paused")
        self.assertEqual(self.store.query("SELECT heartbeat FROM workers WHERE audit_id=?",(healthy,))[0]["heartbeat"],heartbeat)


if __name__=="__main__":unittest.main()
