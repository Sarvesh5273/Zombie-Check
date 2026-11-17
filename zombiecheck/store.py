import json
import hashlib
import math
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from .models import utcnow


class Store:
    def __init__(self, path="data/zombiecheck.sqlite3"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS audits (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
              status TEXT NOT NULL, headers TEXT NOT NULL, config TEXT NOT NULL, input_sha256 TEXT NOT NULL,
              budget REAL NOT NULL, reserved REAL NOT NULL DEFAULT 0, error TEXT);
            CREATE TABLE IF NOT EXISTS rows (
              audit_id TEXT NOT NULL, row_id TEXT NOT NULL, position INTEGER NOT NULL,
              original TEXT NOT NULL, name TEXT NOT NULL, website TEXT NOT NULL,
              status TEXT NOT NULL, raw TEXT, result TEXT, dataset_id TEXT, error TEXT,
              PRIMARY KEY(audit_id,row_id));
            CREATE TABLE IF NOT EXISTS batches (
              id TEXT PRIMARY KEY, audit_id TEXT NOT NULL, number INTEGER NOT NULL, name TEXT NOT NULL,
              row_ids TEXT NOT NULL, status TEXT NOT NULL, dataset_id TEXT, run_id TEXT,
              error TEXT, cost REAL NOT NULL, UNIQUE(audit_id,number));
            CREATE TABLE IF NOT EXISTS snapshots (
              audit_id TEXT NOT NULL,url TEXT NOT NULL, body TEXT NOT NULL, checked_at TEXT NOT NULL,
              PRIMARY KEY(audit_id,url));
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, audit_id TEXT NOT NULL, time TEXT NOT NULL,
              kind TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS calls (
              id INTEGER PRIMARY KEY AUTOINCREMENT, audit_id TEXT NOT NULL, time TEXT NOT NULL,
              service TEXT NOT NULL, operation TEXT NOT NULL, status INTEGER, units INTEGER NOT NULL,
              note TEXT);
            CREATE TABLE IF NOT EXISTS workers (
              audit_id TEXT PRIMARY KEY, token TEXT NOT NULL, pid INTEGER NOT NULL,
              heartbeat REAL NOT NULL,
              FOREIGN KEY(audit_id) REFERENCES audits(id) ON DELETE CASCADE);
            """)
            self.db.commit()
            if "api_reserved" not in [r["name"] for r in self.db.execute("PRAGMA table_info(audits)")]:
                self.db.execute("ALTER TABLE audits ADD COLUMN api_reserved REAL NOT NULL DEFAULT 0")
                self.db.commit()

    def execute(self, sql, params=()):
        with self.lock:
            cur = self.db.execute(sql, params)
            self.db.commit()
            return cur

    def query(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def create_audit(self, parsed, rows, name, config):
        if not math.isfinite(float(config["budget"])) or config["budget"]<0:
            raise ValueError("Budget must be finite and nonnegative")
        config=dict(config,original_rows_sha256=hashlib.sha256(json.dumps([r['original'] for r in rows],ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
        id = str(uuid.uuid4())
        with self.lock, self.db:
            self.db.execute("INSERT INTO audits(id,name,created_at,status,headers,config,input_sha256,budget) VALUES(?,?,?,?,?,?,?,?)",
                            (id, name, utcnow(), "ready", json.dumps(parsed["headers"]), json.dumps(config), parsed["input_sha256"], config["budget"]))
            self.db.executemany("INSERT INTO rows(audit_id,row_id,position,original,name,website,status) VALUES(?,?,?,?,?,?,?)",
                                [(id,r["row_id"],r["position"],json.dumps(r["original"]),r["name"],r["website"],"pending") for r in rows])
        self.event(id,"import",f"Imported {len(rows)} rows; input order and cells preserved.")
        return id

    def audit(self, id):
        records = self.query("SELECT * FROM audits WHERE id=?", (id,))
        if not records:
            raise KeyError("Audit not found")
        r = records[0]
        for key in ("headers", "config"):
            r[key] = json.loads(r[key])
        counts = self.query("SELECT status,COUNT(*) AS count FROM rows WHERE audit_id=? GROUP BY status",(id,))
        r["counts"] = {x["status"]:x["count"] for x in counts}
        r["total"] = sum(r["counts"].values())
        verdicts = self.query("SELECT json_extract(result,'$.verdict') AS verdict,COUNT(*) AS count FROM rows WHERE audit_id=? AND result IS NOT NULL GROUP BY verdict",(id,))
        r["verdicts"] = {x["verdict"] or "unresolved":x["count"] for x in verdicts}
        return r

    def rows(self, id, status=None, limit=None, offset=0):
        sql, params = "SELECT * FROM rows WHERE audit_id=?", [id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY position"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit,offset]
        result = self.query(sql, params)
        for r in result:
            for key in ("original", "raw", "result"):
                r[key] = json.loads(r[key]) if r[key] else None
        return result

    def set_status(self,id,status,error=None):
        self.execute("UPDATE audits SET status=?,error=? WHERE id=?",(status,error,id))

    def row_update(self,audit_id,row_id,**fields):
        allowed = {"status","raw","result","dataset_id","error"}
        if not fields or not fields.keys() <= allowed:
            raise ValueError("Invalid row update")
        params = [json.dumps(v) if k in ("raw","result") and v is not None else v for k,v in fields.items()]
        self.execute("UPDATE rows SET " + ",".join(k+"=?" for k in fields) + " WHERE audit_id=? AND row_id=?",params+[audit_id,row_id])

    def event(self,id,kind,message):
        self.execute("INSERT INTO events(audit_id,time,kind,message) VALUES(?,?,?,?)",(id,utcnow(),kind,message[:4000]))

    def reserve(self,id,cost):
        if not math.isfinite(float(cost)) or cost<0:
            raise ValueError("Reservation must be finite and nonnegative")
        with self.lock, self.db:
            r = self.db.execute("SELECT budget,reserved FROM audits WHERE id=?",(id,)).fetchone()
            if r["reserved"] + cost > r["budget"] + 1e-8:
                return False
            self.db.execute("UPDATE audits SET reserved=reserved+? WHERE id=?",(cost,id))
            return True

    def reserve_request(self,id,cost):
        if not math.isfinite(float(cost)) or cost<0:
            raise ValueError("Request cost must be finite and nonnegative")
        with self.lock,self.db:
            row=self.db.execute("SELECT budget,reserved,api_reserved,config FROM audits WHERE id=?",(id,)).fetchone()
            cap=json.loads(row["config"]).get("request_budget")
            if cap is None:
                return True
            if row["reserved"]+row["api_reserved"]+cost>float(cap)+1e-8:
                return False
            self.db.execute("UPDATE audits SET api_reserved=api_reserved+? WHERE id=?",(cost,id))
            return True

    def refund_request(self,id,cost):
        if not math.isfinite(float(cost)) or cost<0:
            raise ValueError("Refund must be finite and nonnegative")
        self.execute("UPDATE audits SET api_reserved=MAX(0,api_reserved-?) WHERE id=?",(cost,id))

    def snapshot(self,id,url,body=None):
        if body is None:
            records=self.query("SELECT body FROM snapshots WHERE audit_id=? AND url=?",(id,url))
            return json.loads(records[0]["body"]) if records else None
        self.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?)",(id,url,json.dumps(body),utcnow()))

    @staticmethod
    def _pid_alive(pid):
        try:
            os.kill(int(pid),0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # A process outside our permission boundary still exists.
            return True

    def claim_worker(self,audit_id,token,pid,ttl=120):
        """Atomically acquire an audit across independent Store connections.

        A live process with a fresh heartbeat owns the audit. Expired or dead
        owners can be replaced. Heartbeats/releases are fenced by token so an
        old worker cannot renew or delete the replacement's lease.
        """
        if not isinstance(token,str) or not token or int(pid)<=0:
            raise ValueError("Worker needs a nonempty token and positive PID")
        if not math.isfinite(float(ttl)) or float(ttl)<=0:
            raise ValueError("Worker lease TTL must be positive and finite")
        now=time.time()
        with self.lock:
            # BEGIN IMMEDIATE protects the read-and-replace decision from claims
            # arriving through another connection or process.
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if not self.db.execute("SELECT 1 FROM audits WHERE id=?",(audit_id,)).fetchone():
                    raise KeyError("Audit not found")
                owner=self.db.execute("SELECT token,pid,heartbeat FROM workers WHERE audit_id=?",(audit_id,)).fetchone()
                if owner and now-float(owner["heartbeat"])<float(ttl) and self._pid_alive(owner["pid"]):
                    self.db.commit()
                    return False
                self.db.execute("INSERT OR REPLACE INTO workers(audit_id,token,pid,heartbeat) VALUES(?,?,?,?)",
                                (audit_id,token,int(pid),now))
                self.db.commit()
                return True
            except Exception:
                self.db.rollback()
                raise

    def heartbeat_worker(self,audit_id,token):
        return self.execute("UPDATE workers SET heartbeat=? WHERE audit_id=? AND token=?",
                            (time.time(),audit_id,token)).rowcount==1

    def recover_interrupted(self,ttl=120):
        """Pause abandoned audits without disturbing another live worker."""
        if not math.isfinite(float(ttl)) or ttl<=0:
            raise ValueError("Worker lease TTL must be positive and finite")
        now=time.time()
        paused=[]
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                audits=self.db.execute("SELECT id FROM audits WHERE status IN ('running','pausing')").fetchall()
                for audit in audits:
                    owner=self.db.execute("SELECT pid,heartbeat FROM workers WHERE audit_id=?",(audit['id'],)).fetchone()
                    if owner and now-float(owner['heartbeat'])<ttl and self._pid_alive(owner['pid']):
                        continue
                    self.db.execute("UPDATE audits SET status='paused' WHERE id=?",(audit['id'],))
                    self.db.execute("DELETE FROM workers WHERE audit_id=?",(audit['id'],))
                    paused.append(audit['id'])
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        return paused

    def release_worker(self,audit_id,token):
        return self.execute("DELETE FROM workers WHERE audit_id=? AND token=?",
                            (audit_id,token)).rowcount==1

