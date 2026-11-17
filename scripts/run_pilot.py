"""Verify the existing three-company TinySet pilot, without creating another dataset."""
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from zombiecheck.engine import Engine
from zombiecheck.ingest import map_rows,parse_csv,export_csv
from zombiecheck.store import Store
from zombiecheck.tinyfish import TinyFish

store=Store("data/pilot.sqlite3")
parsed=parse_csv("Company,Website\nStripe,https://stripe.com\nSlack,https://slack.com\nInVision,https://www.invisionapp.com\n")
existing=store.query("SELECT id FROM audits WHERE name='Live integration pilot' ORDER BY created_at DESC LIMIT 1")
id=existing[0]["id"] if existing else store.create_audit(parsed,map_rows(parsed,0,1),"Live integration pilot",{"budget":0,"strategy":"triage"})
client=TinyFish(store=store,audit_id=id)
dataset_id="fdfbfe18-78bb-4feb-8001-41ae7a45b994"
returned=client.dataset_rows(dataset_id)
raw={r["data"]["row_id"]:r["data"] for r in returned}
engine=Engine(store)
store.set_status(id,"running")
print(json.dumps({"audit_id":id,"tinyset_dataset_id":dataset_id,"returned_companies":list(raw)}),flush=True)
for row in store.rows(id):
    if row["status"]=="done":
        continue
    data=raw.get(row["name"],{})
    store.row_update(id,row["row_id"],raw=data,dataset_id=dataset_id)
    engine.fast_row(id,row,client,threading.Event(),raw=data)
    r=store.rows(id)[row["position"]]
    print(json.dumps({"company":row["name"],"status":r["status"],"verdict":r["result"].get("verdict"),
                      "signals_verified":r["result"].get("signals_verified"),"identity":r["result"].get("identity")}),flush=True)
store.set_status(id,"complete" if all(r["status"]=="done" for r in store.rows(id)) else "needs_review")
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/pilot.csv").write_text(export_csv(parsed["headers"],store.rows(id)),encoding="utf-8")
Path("artifacts/pilot-report.json").write_text(json.dumps(engine.report(id),indent=2))
print(json.dumps(engine.report(id),indent=2),flush=True)

