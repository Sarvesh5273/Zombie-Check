"""Small REST client. Non-idempotent requests are never blindly retried."""
import json
import os
import subprocess
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .models import SIGNALS, safe_url


class APIError(RuntimeError):
    def __init__(self,status,message,ambiguous=False,retry_after=0):
        super().__init__(message)
        self.status,self.ambiguous,self.retry_after=status,ambiguous,retry_after


class TinyFish:
    def __init__(self, key=None, store=None, audit_id="setup"):
        self.key=key or os.environ.get("TINYFISH_API_KEY","")
        self.store,self.audit_id=store,audit_id
        self.search_lock=threading.Lock()
        self.last_search=0
        self.fetch_lock=threading.Lock()
        self.next_fetch=0

    def request(self,method,url,body=None,service="tinyset",units=1,timeout=120):
        if not self.key:
            raise APIError(401,"TINYFISH_API_KEY is not configured")
        payload=json.dumps(body).encode() if body is not None else None
        req=urllib.request.Request(url,data=payload,method=method,
            headers={"X-API-Key":self.key,"Content-Type":"application/json","Accept":"application/json"})
        retries=4 if method=="GET" or service=="fetch" else 1
        for attempt in range(retries):
            if self.store and service in ("search","fetch"):
                cost=units*(0.005 if service=="search" else 0.001)
                if not self.store.reserve_request(self.audit_id,cost):
                    raise APIError(402,"Build spending cap reached. This audit's conservative request budget is protected.")
            try:
                with urllib.request.urlopen(req,timeout=timeout) as response:
                    value=json.load(response)
                    if self.store and service=="fetch":
                        successful=len(value.get("results",[]))
                        self.store.refund_request(self.audit_id,max(0,units-successful)*0.001)
                    self.log(service,method,response.status,units)
                    return value
            except urllib.error.HTTPError as error:
                self.log(service,method,error.code,units)
                try:
                    data=json.loads(error.read())
                    message=data.get("error",{}).get("message",str(error.code))
                except (ValueError,AttributeError):
                    message=f"TinyFish HTTP {error.code}"
                retry=float(error.headers.get("Retry-After","0") or 0)
                if error.code in (429,500,502,503,504) and attempt+1<retries:
                    time.sleep(min(45,max(retry,2**attempt*2)))
                    continue
                raise APIError(error.code,message,ambiguous=method=="POST" and service not in ("fetch",) and error.code>=500,retry_after=retry)
            except (urllib.error.URLError,TimeoutError,OSError,ValueError) as error:
                self.log(service,method,0,units,type(error).__name__)
                if attempt+1<retries:
                    time.sleep(min(15,2**attempt*2))
                    continue
                raise APIError(0,"Network request failed: "+type(error).__name__,ambiguous=method=="POST" and service!="fetch")

    def log(self,service,operation,status,units=1,note=""):
        if self.store:
            from .models import utcnow
            self.store.execute("INSERT INTO calls(audit_id,time,service,operation,status,units,note) VALUES(?,?,?,?,?,?,?)",
                               (self.audit_id,utcnow(),service,operation,status,units,note))

    def fetch(self,urls):
        urls=list(dict.fromkeys(safe_url(url) for url in urls if safe_url(url)))
        if not urls:
            return {"results":[],"errors":[]}
        if len(urls)>10:
            raise ValueError("TinyFetch batch exceeds 10 URLs")
        with self.fetch_lock:
            slot=max(self.next_fetch,time.monotonic())
            self.next_fetch=slot+len(urls)*0.42
        time.sleep(max(0,slot-time.monotonic()))
        return self.request("POST","https://api.fetch.tinyfish.ai",{
            "urls":urls,"format":"markdown","links":True,"iframe_links":True,"ttl":0,
            "per_url_timeout_ms":45000,
            "purpose":"Verify original company identity and signs of product life, with exact source dates and evidence. Report blocks explicitly."},service="fetch",units=len(urls))

    def search(self,query):
        with self.search_lock:
            time.sleep(max(0,2.1-(time.monotonic()-self.last_search)))
            self.last_search=time.monotonic()
        return self.request("GET","https://api.search.tinyfish.ai?"+urllib.parse.urlencode({
            "query":query,"purpose":"Find the official current website, closure or rebrand for this exact company. Search snippets are discovery only."}),service="search")

    def create_dataset(self,name,entities):
        manifest=[{"company":r["name"],"website":r["website"]} for r in entities]
        description=("Research ONLY companies in the INPUT MANIFEST below. Include EVERY listed company, even closed or acquired companies. "
            "Do not discover substitute companies. Use the provided website to disambiguate names. "
            "Each signal should be its exact official source URL, found by visiting live pages; leave null if unavailable. "
            "Do not use a parent company's activity as evidence that an acquired product is still operating. "
            "INPUT MANIFEST: "+json.dumps(manifest))
        columns=[{"name":"company","type":"string","is_primary_key":True,"format":"Exact company name from the supplied manifest."},
                 {"name":"website","type":"url","is_primary_key":False,"retrieval_hint":"Original website supplied in the manifest. Do not change this URL for redirects."}]
        hints={"blog":"URL of the official blog/news page with dated articles.",
               "release":"URL of the official changelog/product releases or company's official repository releases.",
               "jobs":"URL of official careers page or exact company ATS board.",
               "social":"URL of an official social profile or official GitHub repository activity; verify ownership via the website.",
               "signup":"URL of actual registration/onboarding form; do not submit forms."}
        columns += [{"name":s,"type":"url","is_primary_key":False,"retrieval_hint":hints[s]} for s in SIGNALS]
        columns += [{"name":"identity_evidence","type":"url","is_primary_key":False,"retrieval_hint":"Official evidence of rename, acquisition, discontinuation or closure; null if none."},
                    {"name":"closure_evidence","type":"url","is_primary_key":False,"retrieval_hint":"An explicit closure/shutdown/discontinued announcement for the original company or product; null if none. A redirect alone is not proof of closure."},
                    {"name":"latest_activity_date","type":"date","is_primary_key":False,"retrieval_hint":"Latest actual dated publication/activity on a visited page. Never use copyright date or audit date."}]
        return self.request("POST","https://agent.tinyfish.ai/v1/datasets",{
            "spec":{"name":name,"description":description,"columns":columns},"target_rows":len(entities)},units=len(entities))

    def browser_signup(self,url):
        script=Path(__file__).resolve().parent.parent/"scripts"/"browser_signup.mjs"
        env=dict(os.environ,TINYFISH_API_KEY=self.key)
        response=subprocess.run(["node",str(script),url],capture_output=True,text=True,timeout=125,env=env)
        lines=response.stdout.strip().splitlines()
        if not lines:
            raise APIError(0,"Browser inspection returned no result; no replacement session was started")
        result=json.loads(lines[-1])
        self.log("browser","signup_inspect",201 if result.get("created") else 0,1,result.get("error",""))
        return result

    def queue_intake_inspection(self,url,title,posting_id=''):
        goal=('Inspect only the application or registration entry for '+title+' (posting ID '+posting_id+'). '
              'Click Apply only if needed to reveal the form. Do not fill, submit, sign in, create accounts, '
              'join a talent community or request accommodations. Return JSON with final_url, posting_id, title, '
              'application_form_visible, application_fields (label and type only), and blockage. '
              'Visible controls cannot prove backend acceptance or genuine hiring intent.')
        # Server-enforced step caps require TinyAgent beta. A403 remains visible;
        # never remove the cap and silently launch an unbounded paid run.
        return self.request('POST','https://agent.tinyfish.ai/v1/automation/run-async',{
            'url':url,'goal':goal,'agent_config':{'max_steps':6,'max_duration_seconds':60}},service='agent')

    def agent_run(self,run_id):
        import uuid
        uuid.UUID(run_id)
        return self.request('GET',f'https://agent.tinyfish.ai/v1/runs/{run_id}',service='agent',units=0)

    def dataset(self,id):
        return self.request("GET",f"https://agent.tinyfish.ai/v1/datasets/{id}")

    def populate(self,id,target_rows):
        return self.request("POST",f"https://agent.tinyfish.ai/v1/datasets/{id}/populate",{"target_rows":target_rows,"reset":False})

    def dataset_rows(self,id):
        rows,after=[],None
        while True:
            url=f"https://agent.tinyfish.ai/v1/datasets/{id}/rows?limit=500"
            if after:
                url+="&after="+urllib.parse.quote(after)
            response=self.request("GET",url)
            rows+=response.get("rows",[])
            cursor=response.get("next_cursor")
            if not response.get("truncated") or not cursor:
                return rows
            if cursor==after:
                raise APIError(0,"Repeated TinySet pagination cursor")
            after=cursor

    def find_dataset(self,name):
        cursor=None
        for _ in range(20):
            url="https://agent.tinyfish.ai/v1/datasets?limit=100"
            if cursor:
                url+="&cursor="+urllib.parse.quote(cursor)
            result=self.request("GET",url)
            matches=[d for d in result.get("data",[]) if d.get("name")==name]
            if matches:
                if len(matches)>1:
                    raise APIError(0,"More than one dataset matched recovery name")
                return matches[0]
            cursor=result.get("pagination",{}).get("next_cursor")
            if not cursor:
                return None
        raise APIError(0,"Dataset recovery listing exceeded 2,000 datasets")

