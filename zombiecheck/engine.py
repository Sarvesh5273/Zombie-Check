import concurrent.futures
import json
import hashlib
import os
import re
import threading
import time
import uuid
from urllib.parse import urlparse
from .evidence import (apply_identity_evidence, discover_signal_urls, host, identity_from_page,
                       observe_page, page_text, short_quote, related_host)
from .evidence import inactive_directory_evidence
from .models import SIGNALS, as_object, normalized, safe_url, utcnow
from .rules import classify, RULE_VERSION
from .tinyfish import TinyFish, APIError


class Engine:
    def __init__(self,store,client_factory=None):
        self.store=store
        self.client_factory=client_factory or (lambda id: TinyFish(store=store,audit_id=id))
        self.threads={}
        self.stops={}
        self.lock=threading.Lock()

    def start(self,id):
        with self.lock:
            if id in self.threads and self.threads[id].is_alive():
                return
            self.store.audit(id)
            token=str(uuid.uuid4())
            if not self.store.claim_worker(id,token,os.getpid()):
                return
            stop=threading.Event()
            self.stops[id]=stop
            self.store.set_status(id,"running")
            finished=threading.Event()
            def monitor():
                while not finished.wait(0.2):
                    try:
                        if not self.store.heartbeat_worker(id,token):
                            stop.set()
                            return
                        if self.store.audit(id)["status"]=="pausing":
                            stop.set()
                    except Exception:
                        stop.set()
                        return
            def owned_run():
                watcher=threading.Thread(target=monitor,daemon=True)
                watcher.start()
                try:
                    self.run(id,stop)
                finally:
                    finished.set()
                    watcher.join(timeout=2)
                    self.store.release_worker(id,token)
            thread=threading.Thread(target=owned_run,daemon=True)
            self.threads[id]=thread
            thread.start()

    def pause(self,id):
        with self.lock:
            if id in self.stops:
                self.stops[id].set()
            self.store.set_status(id,"pausing")
        self.store.event(id,"pause","Pause requested. In-flight checks are saved; remote TinySet runs continue and will be reattached on resume.")

    def fetched(self,id,client,urls):
        pages,missing={},[]
        for url in list(dict.fromkeys(safe_url(u) for u in urls if safe_url(u))):
            saved=self.store.snapshot(id,url)
            if saved:
                pages[url]=saved
            else:
                missing.append(url)
        for start in range(0,len(missing),10):
            chunk=missing[start:start+10]
            response=client.fetch(chunk)
            for page in response.get("results",[]):
                page=dict(page,checked_at=utcnow())
                entry={"page":page}
                pages[page["url"]]=entry
                self.store.snapshot(id,page["url"],entry)
            for error in response.get("errors",[]):
                entry={"error":error,"checked_at":utcnow()}
                pages[error["url"]]=entry
                # Terminal missing pages persist. Transient errors are retried by a future row/resume.
                if error.get("error") in ("page_not_found","invalid_url"):
                    self.store.snapshot(id,error["url"],entry)
        return pages

    def fast_row(self,id,row,client,stop,raw=None):
        if stop.is_set():
            return
        self.store.row_update(id,row["row_id"],status="checking",error=None)
        original=row["website"]
        if not original and row["name"]:
            search=client.search(row["name"]+" official company website")
            options=[safe_url(r.get("url")) for r in search.get("results",[]) if safe_url(r.get("url"))]
            original=next((u for u in options if not any(v in host(u) for v in ("linkedin.com","ycombinator.com","crunchbase.com","wikipedia.org"))),"")
        if not original:
            self.store.row_update(id,row["row_id"],status="review",result={"verdict":"","confidence":"insufficient","review_required":True,
                "reason":"No valid public website was supplied or safely discovered.","signals_checked":0,"signals_verified":0,"signals":{},"evidence_links":[]})
            return
        working=dict(row,website=original)
        headers=self.store.audit(id)["headers"]
        reference_idx=next((i for i,h in enumerate(headers) if h.lower() in ("source_url","reference_url","yc_url")),None)
        if reference_idx is not None:
            working["reference_url"]=safe_url(row["original"][reference_idx])
        entries=self.fetched(id,client,[original])
        home_entry=entries.get(original,{})
        home=home_entry.get("page")
        identity=identity_from_page(working,home) if home else {"status":"unknown","canonical_url":original,"url":original,"verified":False,"note":"Homepage could not be read."}
        homepage={"url":original,"final_url":home.get("final_url") if home else None,"quote":short_quote(page_text(home)) if home else "",
                  "verified":bool(home and page_text(home).strip()),"error":home_entry.get("error"),"checked_at":utcnow()}
        urls=discover_signal_urls(home or {},identity.get("canonical_url") or original)
        linked=set(home.get("links",[]) if home else [])
        if raw:
            for s in SIGNALS:
                value=as_object(raw.get(s))
                candidate=safe_url(value.get("url") if value else raw.get(s))
                if candidate:
                    urls[s]=candidate
        entries.update(self.fetched(id,client,list(urls.values())))
        signals={s:observe_page(s,urls[s],page=entries.get(urls[s],{}).get("page"),error=entries.get(urls[s],{}).get("error"),linked=urls[s] in linked,company_url=original) for s in SIGNALS}
        # Blog indexes often omit dates. Inspect linked article pages instead of inventing one.
        for kind in ("blog","release"):
            index=entries.get(urls[kind],{}).get("page")
            if index and not signals[kind].get("date_verified"):
                candidates=[safe_url(u) for u in index.get("links",[]) if safe_url(u) and related_host(u,original) and
                            u.rstrip("/")!=urls[kind].rstrip("/") and
                            urlparse(u).path.startswith(urlparse(urls[kind]).path.rstrip("/")+"/") and
                            not re.search(r"/(?:category|tag|author|page|search|privacy|terms)(?:/|$)",u)][:2]
                for candidate,entry in self.fetched(id,client,candidates).items():
                    if entry.get("page"):
                        observed=observe_page(kind,candidate,entry["page"],linked=True,company_url=original)
                        if observed.get("date_verified") and (not signals[kind].get("latest_date") or observed["latest_date"]>signals[kind]["latest_date"]):
                            signals[kind]=observed
        # Browser checks contribute actual visible-form evidence where text fetch is insufficient.
        if (signals["signup"]["status"] in ("blocked","unknown") and homepage["verified"] and
            identity.get("verified") and not stop.is_set() and hasattr(client,"browser_signup")):
            with self.store.lock:
                count=self.store.query("SELECT COUNT(*) AS n FROM calls WHERE audit_id=? AND service='browser'",(id,))[0]["n"]
                allowed=count<self.store.audit(id)["config"].get("browser_checks",2) and self.store.reserve(id,0.10)
                if allowed:
                    # Reserve an in-flight slot before the network call so parallel workers respect the cap.
                    self.store.execute("INSERT INTO calls(audit_id,time,service,operation,status,units,note) VALUES(?,?,?,?,?,?,?)",
                        (id,utcnow(),"browser","reserved",0,0,"Read-only signup verification slot"))
            if allowed:
                try:
                    inspected=client.browser_signup(urls["signup"])
                    if inspected.get("verified") and related_host(inspected.get("final_url"),original):
                        signals["signup"].update(status="active",verified=True,method="tinybrowser",
                            checked_at=inspected["checked_at"],quote=short_quote(inspected.get("text","")),
                            note=inspected["note"],error=None,url=inspected.get("final_url",urls["signup"]))
                        signals["signup"]["browser_observation"]={k:inspected.get(k) for k in ("fields","buttons","session_id","title","form_observation","form_observations","button_observations","cleanup_confirmed","cleanup_error","creation_status")}
                except Exception as error:
                    self.store.event(id,"browser_error",str(error))
        closure=None
        if home and identity["status"]=="closed":
            closure={"status":"confirmed","url":original,"quote":identity["quote"],"verified":True}
        # Search only ambiguous / under-evidenced identities; all observations are re-fetched.
        provisional=classify(signals,identity,homepage,closure)
        if provisional["review_required"] and row["name"] and not stop.is_set():
            search=client.search(f'{row["name"]} {host(original)} official blog careers signup acquired shutdown')
            candidates=[safe_url(v.get("url")) for v in search.get("results",[]) if safe_url(v.get("url"))][:3]
            if reference_idx is not None and safe_url(row["original"][reference_idx]):
                candidates.append(safe_url(row["original"][reference_idx]))
            research=self.fetched(id,client,candidates)
            for entry in research.values():
                page=entry.get("page")
                if page:
                    found=apply_identity_evidence(working,identity,page)
                    if found:
                        closure=found
                    corroborated=inactive_directory_evidence(working,identity,page,homepage)
                    if corroborated:
                        closure=corroborated
        if raw:
            more=[]
            for key in ("identity_evidence","closure_evidence"):
                value=as_object(raw.get(key))
                url=safe_url(value.get("url") if value else raw.get(key))
                if url:
                    more.append(url)
            for entry in self.fetched(id,client,more).values():
                if entry.get("page"):
                    found=apply_identity_evidence(working,identity,entry["page"])
                    if found:
                        closure=found
        result=classify(signals,identity,homepage,closure)
        status="done" if result["verdict"] and not result["review_required"] else "review"
        self.store.row_update(id,row["row_id"],result=result,status=status)
        self.store.event(id,"row",f'{row["row_id"]} · {row["name"]} · {result["verdict"] or "needs evidence"}')

    def create_batches(self,id,rows):
        audit=self.store.audit(id)
        budget_left=audit["budget"]-audit["reserved"]
        if audit["config"].get("request_budget") is not None:
            budget_left=min(budget_left,float(audit["config"]["request_budget"])-audit["reserved"]-audit.get("api_reserved",0))
        if audit["config"].get("strategy")=="full":
            eligible=rows
        else:
            eligible=rows[:max(0,int((budget_left-0.50)/0.10+1e-6))]
        if not eligible:
            self.store.event(id,"budget","Paid research cap reached. Unresolved rows remain visible and exportable.")
            return
        # Deduplicate identities for research, but fan the results back to every original input row.
        unique,seen=[],set()
        for row in eligible:
            key=(normalized(row["name"]),host(row["website"]))
            if key not in seen:
                unique.append(row)
                seen.add(key)
        current=self.store.query("SELECT MAX(number) AS maximum FROM batches WHERE audit_id=?",(id,))[0]["maximum"] or 0
        for start in range(0,len(unique),25):
            batch=unique[start:start+25]
            cost=round(len(batch)*0.10,2)
            with self.store.lock, self.store.db:
                r=self.store.db.execute("SELECT budget,reserved FROM audits WHERE id=?",(id,)).fetchone()
                if r["reserved"]+cost>r["budget"]+1e-8:
                    break
                current+=1
                name=f"Zombie Check {id} batch {current}"
                self.store.db.execute("UPDATE audits SET reserved=reserved+? WHERE id=?",(cost,id))
                self.store.db.execute("INSERT INTO batches(id,audit_id,number,name,row_ids,status,cost) VALUES(?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()),id,current,name,json.dumps([r["row_id"] for r in batch]),"pending",cost))

    def batch(self,id,batch,client,stop):
        rows={r["row_id"]:r for r in self.store.rows(id)}
        wanted=[rows[k] for k in json.loads(batch["row_ids"])]
        dataset_id=batch["dataset_id"]
        if not dataset_id:
            if batch["status"] in ("creating","ambiguous"):
                recovered=client.find_dataset(batch["name"])
                if recovered:
                    dataset_id=recovered["id"]
                    self.store.event(id,"recovery","Reattached existing remote dataset after interruption.")
                else:
                    self.store.execute("UPDATE batches SET status='ambiguous',error=? WHERE id=?",("Creation outcome uncertain; no duplicate paid request was sent.",batch["id"]))
                    return
            else:
                self.store.execute("UPDATE batches SET status='creating' WHERE id=?",(batch["id"],))
                try:
                    remote=client.create_dataset(batch["name"],wanted)
                    dataset_id=remote.get("id") or remote.get("dataset_id")
                    if not dataset_id:
                        raise APIError(0,"Dataset create did not return an ID",ambiguous=True)
                except APIError as error:
                    status="ambiguous" if error.ambiguous else "retryable" if error.status in (409,429,503) else "failed"
                    self.store.execute("UPDATE batches SET status=?,error=? WHERE id=?",(status,str(error),batch["id"]))
                    self.store.event(id,"api_error",str(error))
                    if error.status==402:
                        stop.set()
                    return
            self.store.execute("UPDATE batches SET dataset_id=?,status='running' WHERE id=?",(dataset_id,batch["id"]))
            for r in wanted:
                self.store.row_update(id,r["row_id"],dataset_id=dataset_id)
        deadline=time.monotonic()+45*60
        if batch["status"]=="partial" and hasattr(client,"populate"):
            remote=client.dataset(dataset_id)
            if remote.get("row_count",len(wanted))<len(wanted):
                self.store.execute("UPDATE batches SET status='repopulating' WHERE id=?",(batch["id"],))
                try:
                    client.populate(dataset_id,len(wanted))
                except APIError as error:
                    self.store.execute("UPDATE batches SET status=?,error=? WHERE id=?",("recovery_required" if error.ambiguous else "partial",str(error),batch["id"]))
                    return
        while not stop.is_set():
            if time.monotonic()>deadline:
                self.store.event(id,"remote_wait","Remote run exceeded 45-minute wait window. Its ID is saved for resume.")
                self.store.set_status(id,"paused")
                stop.set()
                return
            remote=client.dataset(dataset_id)
            run=remote.get("run") or {}
            self.store.execute("UPDATE batches SET run_id=? WHERE id=?",(run.get("id"),batch["id"]))
            if remote.get("status") in ("ready","failed","cancelled"):
                break
            if stop.wait(12):
                return
        if stop.is_set():
            return
        returned=client.dataset_rows(dataset_id)
        matched=set()
        for data_row in returned:
            data=data_row.get("data",{})
            key=str(data.get("row_id") or "")
            matches=[r for r in wanted if r["row_id"]==key]
            if not matches:
                name=str(data.get("company") or data.get("row_id") or "")
                matches=[r for r in wanted if normalized(r["name"])==normalized(name)]
                if len(matches)>1:
                    matches=[r for r in matches if host(data.get("website"))==host(r["website"])]
            if len(matches)!=1:
                self.store.event(id,"reconcile","Rejected unexpected/ambiguous TinySet entity: "+str(data.get("company") or key)[:120])
                continue
            r=matches[0]
            if r["row_id"] in matched:
                self.store.event(id,"reconcile","Duplicate TinySet row ignored: "+r["row_id"])
                continue
            if data.get("website") and host(data["website"])!=host(r["website"]):
                self.store.event(id,"reconcile","TinySet website mismatch; row withheld: "+r["row_id"])
                continue
            matched.add(r["row_id"])
            if r["status"]=="done" and r.get("dataset_id")==dataset_id and r.get("raw"):
                continue
            self.store.row_update(id,r["row_id"],raw=data,dataset_id=dataset_id)
            self.fast_row(id,r,client,stop,raw=data)
            updated=next(x for x in self.store.rows(id) if x["row_id"]==r["row_id"])
            for duplicate in self.store.rows(id):
                if duplicate["row_id"]!=r["row_id"] and normalized(duplicate["name"])==normalized(r["name"]) and host(duplicate["website"])==host(r["website"]):
                    self.store.row_update(id,duplicate["row_id"],raw=data,dataset_id=dataset_id,result=updated["result"],status=updated["status"])
        for r in wanted:
            if r["row_id"] not in matched:
                self.store.row_update(id,r["row_id"],error="TinySet did not return an unambiguous matching entity")
        status="done" if len(matched)==len(wanted) else "partial"
        self.store.execute("UPDATE batches SET status=? WHERE id=?",(status,batch["id"]))
        self.store.event(id,"batch",f"TinySet batch {batch['number']}: matched {len(matched)}/{len(wanted)} inputs.")

    def run(self,id,stop):
        client=self.client_factory(id)
        try:
            audit=self.store.audit(id)
            if audit["config"].get("mode")=="jobs":
                from .jobs import run_jobs
                return run_jobs(self,id,stop)
            # A process interruption can leave an in-flight row. Its source snapshots remain saved.
            self.store.execute("UPDATE rows SET status='pending' WHERE audit_id=? AND status='checking'",(id,))
            for row in self.store.rows(id):
                if row.get("result") and row["result"].get("rule_version") not in (None,RULE_VERSION):
                    self.store.row_update(id,row["row_id"],status="pending")
                    self.store.event(id,"rules",row["row_id"]+" will be re-evaluated from saved evidence after a rules revision.")
            transient={"timeout","target_unreachable","proxy_error","target_http_error","no_response"}
            for row in self.store.rows(id,status="review"):
                failures=[s.get("error") for s in (row.get("result") or {}).get("signals",{}).values()]
                if row.get("error") or any(e in transient for e in failures):
                    self.store.row_update(id,row["row_id"],status="pending")
            pending=self.store.rows(id,status="pending")
            if audit["config"].get("strategy")!="full":
                self.store.event(id,"phase","Checking five signals with live TinyFetch. TinySearch resolves ambiguous identities.")
                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                    futures={pool.submit(self.fast_row,id,r,client,stop):r for r in pending}
                    for future in concurrent.futures.as_completed(futures):
                        row=futures[future]
                        try:
                            future.result()
                        except Exception as error:
                            self.store.row_update(id,row["row_id"],status="review",error=str(error))
                            self.store.event(id,"row_error",row["row_id"]+": "+str(error))
                            if isinstance(error,APIError) and error.status==402:
                                stop.set()
            if stop.is_set():
                self.store.set_status(id,"paused")
                return
            existing=self.store.query("SELECT * FROM batches WHERE audit_id=? ORDER BY number",(id,))
            if not existing:
                candidates=self.store.rows(id,status="pending") if audit["config"].get("strategy")=="full" else self.store.rows(id,status="review")
                if not candidates and audit["budget"]-audit["reserved"]>=0.80:
                    candidates=self.store.rows(id,limit=3)
                    self.store.event(id,"validation","TinySet independently checks three resolved entities; its returned source pages will be verified.")
                self.create_batches(id,candidates)
                existing=self.store.query("SELECT * FROM batches WHERE audit_id=? ORDER BY number",(id,))
            for batch in existing:
                if stop.is_set():
                    break
                if batch["status"]=="retryable":
                    self.store.execute("UPDATE batches SET status='pending' WHERE id=?",(batch["id"],))
                    batch=dict(batch,status="pending")
                if batch["status"] not in ("done","failed","recovery_required"):
                    self.batch(id,batch,client,stop)
            if stop.is_set():
                self.store.set_status(id,"paused")
                return
            result=self.store.audit(id)
            complete=result["counts"].get("done",0)==result["total"]
            self.store.set_status(id,"complete" if complete else "needs_review")
            self.store.event(id,"finish","Every row has a verified verdict." if complete else "Checks saved. Unresolved rows need more evidence; this run does not pass the full-completion gate.")
        except Exception as error:
            self.store.set_status(id,"error",str(error))
            self.store.event(id,"error",str(error))

    def report(self,id):
        audit=self.store.audit(id)
        rows=self.store.rows(id)
        preserved=hashlib.sha256(json.dumps([r['original'] for r in rows],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==audit['config'].get('original_rows_sha256')
        all_verdicts=all(r["result"] and r["result"].get("verdict") for r in rows)
        four_checks=all((r["result"] or {}).get("signals_checked",0)>=4 for r in rows)
        no_review=all(not (r["result"] or {"review_required":True}).get("review_required",True) for r in rows)
        evidence_present=all(bool((r["result"] or {}).get("evidence_links")) and
                             any(s.get("verified") and s.get("url") for s in (r["result"] or {}).get("signals",{}).values())
                             for r in rows)
        calls=self.store.query("SELECT service,COUNT(*) AS requests,SUM(units) AS units FROM calls WHERE audit_id=? AND status BETWEEN 200 AND 299 GROUP BY service",(id,))
        endpoints=[r["service"] for r in calls]
        jobs_mode=audit["config"].get("mode")=="jobs"
        job_state=audit["config"].get("jobs_state",{})
        researched_employers=sum(bool(e.get("verified") and e.get("raw")) for e in job_state.get("employers",{}).values())
        return {"audit_id":id,"name":audit["name"],"created_at":audit["created_at"],"generated_at":utcnow(),
                "input_sha256":audit["input_sha256"],"input_rows":len(rows),"output_rows":len(rows),
                "counts":audit["counts"],"verdicts":audit["verdicts"],"status":audit["status"],
                "paid_budget_usd":audit["budget"],"reserved_usd":audit["reserved"],
                "request_budget_usd":audit["config"].get("request_budget"),"api_request_upper_bound_usd":audit.get("api_reserved",0),
                "mode":audit["config"].get("mode","companies"),"tinyset_employers_researched":researched_employers if jobs_mode else None,
                "gates":{"at_least_500_rows":len(rows)>=500,"all_rows_have_verdicts":all_verdicts,
                         "four_live_checks_every_row":four_checks,"no_unresolved_reviews":no_review,
                         "every_verdict_has_evidence":evidence_present,
                         "tinyset_used":"tinyset" in endpoints,"original_rows_preserved":preserved},
                "submission_ready":len(rows)>=500 and all_verdicts and four_checks and no_review and evidence_present and preserved and "tinyset" in endpoints,
                "services":calls,"notes":["TinyFetch calls used ttl=0. Saved snapshots are reused within this audit only for resume.",
                  "Job intake checks establish public ATS question configuration and record rendered-page scope separately. No applications were submitted; genuine vacancy intent and backend acceptance are unverified." if jobs_mode else "Signup checks establish a reachable registration entry; no accounts were created.",
                  "TinySet researches each unique employer once; those sourced context signals are joined to its distinct roles. Each role gets independent live availability and intake checks." if jobs_mode else "Directory data supplied names and URLs only; directory status labels were not used for verdicts."]}

