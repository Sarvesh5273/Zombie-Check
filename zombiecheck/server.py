import hmac
import json
import mimetypes
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .engine import Engine
from .ingest import parse_csv, map_rows, export_csv, job_column_mapping
from .store import Store
from .models import normalized
from .evidence import host as url_host

ROOT=Path(__file__).resolve().parent.parent


def serve(host="127.0.0.1",port=8765,db=None):
    token=os.environ.get("ZOMBIECHECK_ACCESS_TOKEN","")
    if host not in ("127.0.0.1","localhost","::1") and not token:
        raise SystemExit("Set ZOMBIECHECK_ACCESS_TOKEN before exposing the paid API outside localhost.")
    store=Store(db or os.environ.get("ZOMBIECHECK_DB","data/zombiecheck.sqlite3"))
    engine=Engine(store)
    # Interrupted jobs are paused for explicit resume, retaining remote runs and results.
    store.recover_interrupted()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,fmt,*args):
            return

        def response(self,value,status=200,kind="application/json; charset=utf-8",filename=None):
            payload=json.dumps(value).encode() if kind.startswith("application/json") else value if isinstance(value,bytes) else value.encode()
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            if filename:
                self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            origin=self.headers.get("Origin")
            expected=self.headers.get("Host")
            if origin and urllib.parse.urlparse(origin).netloc!=expected:
                self.response({"error":"Origin not allowed"},403)
                return False
            if token and not hmac.compare_digest(self.headers.get("X-Audit-Token","").encode(),token.encode()):
                self.response({"error":"An access token is required"},401)
                return False
            return True

        def body(self):
            size=int(self.headers.get("Content-Length",0))
            if size>22*1024*1024:
                raise ValueError("Request exceeds 22 MB")
            return json.loads(self.rfile.read(size).decode("utf-8"))

        def do_GET(self):
            path=urllib.parse.urlparse(self.path).path
            try:
                if path.startswith("/api/"):
                    if not self.authorized():
                        return
                    if path=="/api/config":
                        return self.response({"key_configured":bool(os.environ.get("TINYFISH_API_KEY")),"budget_default":float(os.environ.get("ZOMBIECHECK_BUDGET","5")),"version":"0.1.0"})
                    if path=="/api/audits":
                        ids=store.query("SELECT id FROM audits ORDER BY created_at DESC LIMIT 30")
                        return self.response({"audits":[store.audit(r["id"]) for r in ids]})
                    match=re.fullmatch(r"/api/audits/([0-9a-f-]+)(?:/(rows|events|report|export))?",path)
                    if not match:
                        return self.response({"error":"Not found"},404)
                    id,action=match.groups()
                    audit=store.audit(id)
                    if action=="rows":
                        query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                        limit=min(500,max(1,int(query.get("limit",[100])[0])))
                        offset=max(0,int(query.get("offset",[0])[0]))
                        return self.response({"rows":store.rows(id,limit=limit,offset=offset),"total":audit["total"]})
                    if action=="events":
                        return self.response({"events":store.query("SELECT * FROM events WHERE audit_id=? ORDER BY id DESC LIMIT 80",(id,))})
                    if action=="report":
                        return self.response(engine.report(id))
                    if action=="export":
                        return self.response("\ufeff"+export_csv(audit["headers"],store.rows(id)),kind="text/csv; charset=utf-8",filename="zombie-check.csv")
                    return self.response(audit)
                file=ROOT/"web"/({"/":"index.html"}.get(path,path.lstrip("/")))
                resolved=file.resolve()
                if ROOT/"web" not in resolved.parents or not file.is_file():
                    return self.response({"error":"Not found"},404)
                return self.response(file.read_bytes(),kind=mimetypes.guess_type(file)[0] or "application/octet-stream")
            except KeyError:
                self.response({"error":"Audit not found"},404)
            except (ValueError,TypeError) as error:
                self.response({"error":str(error)},400)

        def do_POST(self):
            if not self.authorized():
                return
            path=urllib.parse.urlparse(self.path).path
            try:
                body=self.body()
                if path=="/api/preview":
                    parsed=parse_csv(body["csv"])
                    return self.response(dict(parsed,rows=parsed["rows"][:6]))
                if path=="/api/audits":
                    parsed=parse_csv(body["csv"])
                    name_col=int(body.get("name_column",parsed["name_column"]))
                    url_col=body.get("url_column",parsed["url_column"])
                    url_col=int(url_col) if url_col is not None else None
                    budget=float(body.get("budget",os.environ.get("ZOMBIECHECK_BUDGET","5")))
                    if not 0<=budget<=100:
                        raise ValueError("Budget must be between $0 and $100")
                    strategy=body.get("strategy","triage")
                    if strategy not in ("triage","full"):
                        raise ValueError("Strategy must be triage or full")
                    mapped=map_rows(parsed,name_col,url_col)
                    mode=body.get("mode","auto")
                    if mode not in ("auto","companies","jobs"):
                        raise ValueError("Mode must be auto, companies, or jobs")
                    mode=parsed["detected_mode"] if mode=="auto" else mode
                    unique_count=len(set((normalized(r["name"]),url_host(r["website"])) for r in mapped))
                    if strategy=="full" and mode!="jobs" and budget+1e-8<unique_count*0.1:
                        raise ValueError("Full TinySet coverage needs $0.10 per unique researched company. Increase the cap or select budget triage.")
                    config={"name_column":name_col,"url_column":url_col,"budget":budget,"request_budget":budget,"strategy":strategy,"mode":mode}
                    if mode=='jobs':
                        config['job_columns']=job_column_mapping(parsed['headers'],body.get('job_columns'))
                    id=store.create_audit(parsed,mapped,str(body.get("name","Company audit"))[:200],config)
                    return self.response(store.audit(id),201)
                match=re.fullmatch(r"/api/audits/([0-9a-f-]+)/(start|pause)",path)
                if not match:
                    return self.response({"error":"Not found"},404)
                id,action=match.groups()
                if action=="start":
                    engine.start(id)
                else:
                    engine.pause(id)
                return self.response(store.audit(id))
            except KeyError as error:
                self.response({"error":"Missing or unknown field: "+str(error)},400)
            except (ValueError,TypeError) as error:
                self.response({"error":str(error)},400)

    print(f"Zombie Check listening on http://{host}:{port}",flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()

