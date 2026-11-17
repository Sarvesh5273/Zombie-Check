"""Start only the three-employer TinySet run for the saved 500-job proof."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from zombiecheck.models import utcnow
from zombiecheck.store import Store
from zombiecheck.tinyfish import TinyFish

id="857949de-0d18-4951-9598-cef63cba4e55"
store=Store();audit=store.audit(id);cfg=audit["config"]
if cfg.get("jobs_state"):
    print("Employer run already has saved state; normal resume will recover/poll it.")
    raise SystemExit(0)
cost=.30
if not store.reserve(id,cost):
    raise SystemExit("The employer research budget is insufficient")
name=f"Zombie Check {id} job employers 1"
state={"version":"jobs-1.0","created_at":utcnow(),"employers":{},"batches":[{
    "number":1,"name":name,"employer_keys":["cloudflare|cloudflare.com","datadog|datadoghq.com","stripe|stripe.com"],
    "phase":"creating","reserved":True,"cost":cost,"reservation_before":0,"attempts":1}]}
cfg["jobs_state"]=state
store.execute("UPDATE audits SET config=? WHERE id=?",(json.dumps(cfg),id))
client=TinyFish(store=store,audit_id=id)
data=client.create_dataset(name,[{"name":"Stripe","website":"https://stripe.com"},
    {"name":"Datadog","website":"https://www.datadoghq.com"},{"name":"Cloudflare","website":"https://www.cloudflare.com"}])
state["batches"][0].update(dataset_id=data.get("id",data.get("dataset_id")),phase="running")
cfg["jobs_state"]=state
store.execute("UPDATE audits SET config=? WHERE id=?",(json.dumps(cfg),id))
print(json.dumps({"audit_id":id,"employer_dataset_id":state["batches"][0]["dataset_id"],"target_rows":3,"reserved_cost":cost}))
