#!/usr/bin/env python3
"""Build a real public job-post input from official employer Greenhouse feeds.

Read-only: no applications, account creation, API keys or paid services.
The source feed establishes which postings were publicly listed at retrieval,
not whether they represent genuine funded vacancies or active hiring intent.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BOARDS = [
    {"employer": "Stripe", "token": "stripe", "website": "https://stripe.com", "careers_url": "https://stripe.com/careers"},
    {"employer": "Datadog", "token": "datadog", "website": "https://www.datadoghq.com", "careers_url": "https://careers.datadoghq.com/"},
    {"employer": "Cloudflare", "token": "cloudflare", "website": "https://www.cloudflare.com", "careers_url": "https://www.cloudflare.com/careers/"},
]
DOCS_URL = "https://developers.greenhouse.io/job-board.html"
FIELDS = ["employer", "title", "job_url", "job_id", "employer_website", "board_url", "job_api_url", "source_url", "listed_updated_at"]


def fetch_json(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ZombieCheck-public-job-input/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(30 * 1024 * 1024)
        return json.loads(raw), hashlib.sha256(raw).hexdigest(), response.geturl()


def fetch_board(config):
    token = str(config["token"])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid Greenhouse board token")
    base = "https://boards-api.greenhouse.io/v1/boards/" + urllib.parse.quote(token, safe="")
    feed_url = base + "/jobs?content=true"
    try:
        data, digest, final_url = fetch_json(feed_url)
        metadata, _, metadata_final = fetch_json(base)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        return {"employer": config["employer"], "token": token, "source_url": feed_url, "available": False, "error": str(error), "jobs": []}
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return {"employer": config["employer"], "token": token, "source_url": feed_url, "available": False, "error": "Unexpected public feed schema", "jobs": []}
    name = str(metadata.get("name") or config["employer"])
    jobs = []
    for job in data["jobs"]:
        id = str(job.get("id") or "")
        title = str(job.get("title") or "").strip()
        url = str(job.get("absolute_url") or "").strip()
        parsed = urllib.parse.urlparse(url)
        if not id.isdigit() or not title or parsed.scheme not in ("https", "http") or not parsed.hostname:
            continue
        jobs.append({"employer": config["employer"], "title": title, "job_url": url,
                     "job_id": f"greenhouse:{token}:{id}", "employer_website": config["website"],
                     "board_url": config["careers_url"], "job_api_url": base+"/jobs/"+id+"?questions=true",
                     "source_url": feed_url, "listed_updated_at": str(job.get("updated_at") or "")})
    return {"employer": config["employer"], "board_name": name, "token": token,
            "source_url": feed_url, "final_url": final_url, "metadata_url": base,
            "metadata_final_url": metadata_final, "official_careers_url": config["careers_url"],
            "available": True, "source_sha256": digest, "public_job_count": len(data["jobs"]),
            "eligible_job_count": len(jobs), "jobs": jobs}


def select_jobs(boards, count, seed):
    buckets = []
    for board in boards:
        values = {job["job_id"]: job for job in board.get("jobs", [])}
        ranked = sorted(values.values(), key=lambda job: hashlib.sha256(f"{seed}:{job['job_id']}".encode()).hexdigest())
        buckets.append(ranked)
    available = len({job["job_id"] for bucket in buckets for job in bucket})
    if available < count:
        raise ValueError(f"Only {available} eligible public unique postings; cannot generate {count} real rows")
    selected, seen, offsets = [], set(), [0] * len(buckets)
    # Round-robin a hash-ranked list from each employer so one large board does
    # not dominate the sample. No status, age or vacancy-intent filter is used.
    while len(selected) < count:
        progressed = False
        for i, bucket in enumerate(buckets):
            while offsets[i] < len(bucket):
                job = bucket[offsets[i]]
                offsets[i] += 1
                if job["job_id"] not in seen:
                    selected.append(job)
                    seen.add(job["job_id"])
                    progressed = True
                    break
            if len(selected) == count:
                break
        if not progressed:
            raise ValueError("Input selection exhausted unexpectedly")
    return selected, available


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="examples/jobs-500.csv")
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--boards-json", help="JSON array of employer/token/website/careers_url objects; defaults are demo sources only")
    parser.add_argument("--seed", default="zombie-check-job-demo-2026-11-17")
    parser.add_argument("--probe", action="store_true", help="Report feed availability/counts only; do not create an export")
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("Row count must be positive")
    configs = json.loads(Path(args.boards_json).read_text()) if args.boards_json else DEFAULT_BOARDS
    if not isinstance(configs, list) or not configs:
        parser.error("Provide at least one board configuration")
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(configs))) as pool:
        boards = list(pool.map(fetch_board, configs))
    finished = dt.datetime.now(dt.timezone.utc).isoformat()
    public = [{k: v for k, v in board.items() if k != "jobs"} for board in boards]
    available = sum(board.get("eligible_job_count", 0) for board in boards)
    if args.probe:
        print(json.dumps({"started_at": started, "finished_at": finished, "eligible_postings": available, "boards": public}, indent=2))
        return
    selected, unique_total = select_jobs(boards, args.rows, args.seed)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(selected)
    text = output.getvalue()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    counts = {}
    for job in selected:
        counts[job["employer"]] = counts.get(job["employer"], 0) + 1
    provenance = {"name": f"Official employer public job-board sample ({args.rows} postings)",
        "retrieval_started_at": started, "retrieval_finished_at": finished, "docs_url": DOCS_URL,
        "boards": public, "available_unique_postings": unique_total, "exported_rows": len(selected),
        "exported_employer_counts": counts, "fields": FIELDS,
        "csv_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "selection": {"method": "Round-robin per-employer SHA-256(seed:provider_token_job_id) ranking", "seed": args.seed,
                      "filters": "Only valid public posting ID, title and URL; no age/status/intent filter"},
        "scope": ["These are publicly listed postings in the employer's official ATS feed at retrieval time.",
                  "A public listing does not prove a funded vacancy, recruiter attention, applicant response, or hiring intent.",
                  "listed_updated_at is the feed's admin update timestamp, not necessarily original publish date or genuine recent hiring.",
                  "Verification must independently re-fetch each job API/page and application question/intake evidence live.",
                  "Shared employer activity must be source-checked and labeled as employer context, not job-specific activity.",
                  "No applications were submitted and no candidate information was collected.",
                  "Source descriptions are processed in memory; the distributed input contains posting facts and URLs only."]}
    meta_path = destination.with_suffix(".provenance.json")
    meta_path.write_text(json.dumps(provenance, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"csv": str(destination), "provenance": str(meta_path), "rows": len(selected),
                      "available_unique_postings": unique_total, "employers": counts, "boards": public}, indent=2))


if __name__ == "__main__":
    main()

