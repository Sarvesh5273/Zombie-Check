"""Record and verify real checkpoint preservation; never generates fake audit data."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from zombiecheck.store import Store
from zombiecheck.models import utcnow

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

p=argparse.ArgumentParser()
p.add_argument("action",choices=["before","verify"])
p.add_argument("audit_id")
p.add_argument("--db",default="data/zombiecheck.sqlite3")
p.add_argument("--marker",default="artifacts/resume-before.json")
p.add_argument('--output',default='artifacts/resume-proof.json')
a=p.parse_args();s=Store(a.db);rows=s.rows(a.audit_id)
if a.action=="before":
    marker={"audit_id":a.audit_id,"recorded_at":utcnow(),"input_rows":len(rows),
            "originals_hash":digest([r["original"] for r in rows]),
            "completed":{r["row_id"]:digest(r["result"]) for r in rows if r["status"]=="done"},
            "source_snapshots":s.query("SELECT COUNT(*) AS n FROM snapshots WHERE audit_id=?",(a.audit_id,))[0]["n"]}
    Path(a.marker).parent.mkdir(parents=True,exist_ok=True)
    Path(a.marker).write_text(json.dumps(marker,indent=2))
    print(json.dumps({"checkpointed_completed_rows":len(marker["completed"]),"input_rows":len(rows),"snapshot_count":marker["source_snapshots"]}))
else:
    marker=json.loads(Path(a.marker).read_text())
    byid={r["row_id"]:r for r in rows}
    preserved=all(id in byid and digest(byid[id]["result"])==hash for id,hash in marker["completed"].items())
    progressed=sum(r["status"]=="done" for r in rows)>len(marker["completed"])
    report={"audit_id":a.audit_id,"verified_at":utcnow(),"baseline_completed":len(marker["completed"]),
            "now_completed":sum(r["status"]=="done" for r in rows),"completed_results_unchanged":preserved,
            "original_rows_unchanged":digest([r["original"] for r in rows])==marker["originals_hash"],
            "progress_after_resume":progressed,"pass":preserved and progressed and len(rows)==marker["input_rows"]}
    Path(a.output).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    sys.exit(0 if report["pass"] else 1)
