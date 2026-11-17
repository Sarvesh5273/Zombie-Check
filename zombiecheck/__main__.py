import argparse
import json
import os
import time
from pathlib import Path
from .engine import Engine
from .ingest import parse_csv, map_rows, export_csv, job_column_mapping
from .server import serve
from .store import Store


def main():
    p=argparse.ArgumentParser(description="Audit company lists against live pages, with TinySet, TinySearch and TinyFetch.")
    p.add_argument("--db",default=os.environ.get("ZOMBIECHECK_DB","data/zombiecheck.sqlite3"))
    sub=p.add_subparsers(dest="command",required=True)
    s=sub.add_parser("serve");s.add_argument("--port",type=int,default=8765);s.add_argument("--host",default="127.0.0.1")
    i=sub.add_parser("import");i.add_argument("file");i.add_argument("--name",default="Company audit");i.add_argument("--budget",type=float,default=5);i.add_argument("--strategy",choices=["triage","full"],default="triage");i.add_argument("--name-column");i.add_argument("--url-column");i.add_argument("--mode",choices=["auto","companies","jobs"],default="auto");i.add_argument('--job-columns',help='JSON object mapping employer, employer_website, title, job_url and optional board_token/API fields to headings')
    for command in ("run","resume","report","export"):
        c=sub.add_parser(command);c.add_argument("audit_id")
        if command=="export":c.add_argument("--output",required=True)
    inspection=sub.add_parser('inspect');inspection.add_argument('audit_id');inspection.add_argument('--row',required=True);inspection.add_argument('--method',choices=['browser','agent'],default='browser');inspection.add_argument('--run-id',help='Reattach an already started TinyAgent run, without launching or charging a new run')
    a=p.parse_args()
    if a.command=="serve":
        return serve(a.host,a.port,a.db)
    store=Store(a.db);engine=Engine(store)
    if a.command=="import":
        parsed=parse_csv(Path(a.file).read_text(encoding="utf-8-sig"))
        name=parsed["headers"].index(a.name_column) if a.name_column else parsed["name_column"]
        url=parsed["headers"].index(a.url_column) if a.url_column else parsed["url_column"]
        if a.budget<0:raise SystemExit("Budget cannot be negative")
        mode=parsed["detected_mode"] if a.mode=="auto" else a.mode
        config={"name_column":name,"url_column":url,"budget":a.budget,"request_budget":a.budget,"strategy":a.strategy,"mode":mode}
        if mode=='jobs':
            config['job_columns']=job_column_mapping(parsed['headers'],json.loads(a.job_columns) if a.job_columns else None)
        id=store.create_audit(parsed,map_rows(parsed,name,url),a.name,config)
        estimate=round(parsed["row_count"]*0.1,2)
        if mode=="jobs" and "employer" in parsed["headers"] and "employer_website" in parsed["headers"]:
            e,w=parsed["headers"].index("employer"),parsed["headers"].index("employer_website")
            estimate=round(len(set((r[e],r[w]) for r in parsed["rows"]))*0.1,2)
        print(json.dumps({"audit_id":id,"rows":parsed["row_count"],"mode":mode,"estimated_tinyset_cost":estimate}))
    elif a.command in ("run","resume"):
        engine.start(a.audit_id)
        if a.audit_id not in engine.threads:
            print("An existing worker already owns this audit. Use the server to follow progress or request pause.")
            return
        try:
            while engine.threads[a.audit_id].is_alive():
                result=store.audit(a.audit_id)
                print(json.dumps({"status":result["status"],"counts":result["counts"],"total":result["total"]}),flush=True)
                engine.threads[a.audit_id].join(timeout=20)
        except KeyboardInterrupt:
            engine.pause(a.audit_id)
            print("Pause requested; checkpoints retained. Resume with the same audit ID.")
        print(json.dumps(engine.report(a.audit_id),indent=2))
    elif a.command=='inspect':
        from .inspect import inspect_intake
        print(json.dumps(inspect_intake(engine,a.audit_id,a.row,a.method,a.run_id),ensure_ascii=False,indent=2))
    elif a.command=="report":
        print(json.dumps(engine.report(a.audit_id),indent=2))
    elif a.command=="export":
        audit=store.audit(a.audit_id)
        Path(a.output).write_text("\ufeff"+export_csv(audit["headers"],store.rows(a.audit_id)),encoding="utf-8")
        print(a.output)


if __name__=="__main__":main()

