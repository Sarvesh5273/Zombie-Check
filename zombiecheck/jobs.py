"""Resumable public job-post health checks with shared TinySet employer context.

This module never submits applications. A configured question schema establishes
public intake configuration, not a funded vacancy or successful submission.
"""
import concurrent.futures
import copy
import datetime as dt
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .evidence import discover_signal_urls, host, observe_page, related_host, short_quote
from .models import SIGNALS, as_object, normalized, safe_url, utcnow
from .tinyfish import APIError
from .ingest import job_column_mapping

JOB_RULE_VERSION = "jobs-1.0"
SHARED = ("blog", "release", "social")


def repair_markdown_json(text):
    r"""Undo invalid escapes inside JSON strings, preserving valid paired escapes.

    In particular, a literal JSON \\* is retained; Markdown's single \* is
    repaired. Advancing two characters for a valid escape prevents treating
    the second slash of a valid \\ pair as an independent Markdown escape.
    """
    output, in_string, index = [], False, 0
    pairs = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}
    while index < len(text):
        char = text[index]
        if char == '"':
            in_string = not in_string
            output.append(char)
            index += 1
        elif in_string and char == "\\" and index+1 < len(text):
            escaped = text[index+1]
            valid_unicode = escaped=="u" and bool(re.fullmatch(r"[0-9a-fA-F]{4}", text[index+2:index+6]))
            if escaped in pairs or valid_unicode:
                output.extend((char, escaped))
            else:
                output.append(escaped)
            index += 2
        else:
            output.append(char)
            index += 1
    return "".join(output)


def parse_json_page(entry):
    r"""Repair invalid Markdown JSON escapes; preserve valid \n/\u/\\ pairs."""
    page = (entry or {}).get("page")
    if not page:
        error = (entry or {}).get("error") or {"error": "no_response"}
        return None, error
    text = page.get("text")
    if isinstance(text, dict):
        return text, None
    if not isinstance(text, str):
        return None, {"error": "invalid_json_source"}
    text = text.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", text, re.S)
        if match:
            text = match.group(1)
    try:
        body = json.loads(repair_markdown_json(text))
        return (body, None) if isinstance(body, dict) else (None, {"error": "invalid_json_source"})
    except ValueError:
        return None, {"error": "invalid_json_source"}


def _name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip().casefold()
    return re.sub(r"(?:[, ]+(?:inc\.?|llc|ltd\.?|limited|corporation|corp\.?|careers|jobs))+$", "", value).strip()


def _url_identity(value, posting_id=None):
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").casefold().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    greenhouse = re.fullmatch(r"/([A-Za-z0-9_-]+)/jobs/(\d+)", path)
    if hostname in ("boards.greenhouse.io", "job-boards.greenhouse.io") and greenhouse:
        hostname = "job-boards.greenhouse.io"
        path_id = greenhouse.group(2)
    else:
        numeric_path = re.search(r"/(\d+)/?$", path)
        path_id = numeric_path.group(1) if numeric_path else None
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if key.startswith("utm_") or key in ("gh_src", "ref", "referral", "from", "t"):
            continue
        # gh_jid is identity on Stripe's search URL, but redundant when the
        # same posting ID is already encoded in an official detail path.
        if key=="gh_jid" and path_id and item==path_id and (not posting_id or item==posting_id):
            continue
        query.append((key, item))
    return (parsed.scheme.casefold(), hostname, path, tuple(sorted(query)))


def _read_fields(audit, row):
    original = dict(zip(audit["headers"], row["original"]))
    mappings = job_column_mapping(audit['headers'],audit["config"].get("job_columns", {}))
    def get(field, fallback=""):
        key = mappings.get(field, field)
        if isinstance(key, int):
            return row["original"][key] if 0 <= key < len(row["original"]) else fallback
        return original.get(key, fallback)
    values = {field: str(get(field) or "").strip() for field in (
        "employer", "title", "job_url", "job_id", "employer_website", "board_url", "board_token", "job_api_url", "source_url")}
    values["title"] = values["title"] or row["name"]
    values["job_url"] = values["job_url"] or row["website"]
    if not values["employer"] or not safe_url(values["job_url"]) or not safe_url(values["employer_website"]):
        raise ValueError("Job rows require employer, exact public job URL, and employer website.")
    public = urlparse(values['job_url'])
    native = re.fullmatch(r'/([A-Za-z0-9_-]+)/jobs/(\d+)/?',public.path) if public.hostname in ('boards.greenhouse.io','job-boards.greenhouse.io') else None
    composite = re.fullmatch(r'greenhouse:([A-Za-z0-9_-]+):(\d+)',values['job_id'])
    if not values['job_api_url']:
        token = native.group(1) if native else composite.group(1) if composite else values['board_token']
        posting_id = native.group(2) if native else composite.group(2) if composite else dict(parse_qsl(public.query)).get('gh_jid','')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',token) or not re.fullmatch(r'\d+',posting_id):
            raise ValueError('Use an exact Greenhouse posting URL or supply its board token and official posting ID/API URL. Other ATS providers need an adapter.')
        values['job_api_url']=f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{posting_id}?questions=true'
    parsed = urlparse(values["job_api_url"])
    match = re.fullmatch(r"/v1/boards/([A-Za-z0-9_-]+)/jobs/(\d+)/?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "boards-api.greenhouse.io" or not match:
        raise ValueError("A valid official Greenhouse job_api_url is required; other providers need an adapter.")
    token, posting_id = match.groups()
    if native and native.groups() != (token,posting_id):
        raise ValueError('Public Greenhouse posting URL disagrees with the supplied API URL.')
    if values['board_token'] and values['board_token'] != token:
        raise ValueError('Supplied board token disagrees with the exact posting URL.')
    if not values['job_id']:
        values['job_id']=f'greenhouse:{token}:{posting_id}'
    if values["job_id"] not in (posting_id, f"greenhouse:{token}:{posting_id}"):
        raise ValueError("Original job ID does not match its official posting API URL.")
    for query_key, query_value in parse_qsl(urlparse(values["job_url"]).query):
        if query_key=="gh_jid" and query_value!=posting_id:
            raise ValueError("Original public job URL selects a different Greenhouse posting ID.")
    query = dict(parse_qsl(parsed.query))
    query["questions"] = "true"
    values["job_api_url"] = urlunparse(parsed._replace(query=urlencode(query), fragment=""))
    source = values["source_url"] or f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    source_parsed = urlparse(source)
    if source_parsed.scheme != "https" or source_parsed.hostname != "boards-api.greenhouse.io" or source_parsed.path.rstrip("/") != f"/v1/boards/{token}/jobs":
        raise ValueError("Source feed is not the exact official board for this job.")
    values.update(source_url=source, token=token, posting_id=posting_id,
                  metadata_url=f"https://boards-api.greenhouse.io/v1/boards/{token}",
                  employer_key=_name(values["employer"])+"|"+host(values["employer_website"]))
    return values


def _state(store, id):
    rows = store.query("SELECT config FROM audits WHERE id=?", (id,))
    return json.loads(rows[0]["config"]).get("jobs_state", {})


def _save_state(store, id, state):
    with store.lock:
        config = json.loads(store.query("SELECT config FROM audits WHERE id=?", (id,))[0]["config"])
        config["jobs_state"] = copy.deepcopy(state)
        store.execute("UPDATE audits SET config=? WHERE id=?", (json.dumps(config), id))


def _reserve_batch(store, id, state, batch):
    """Persist intent before reservation; recover the crash gap under one owner."""
    if batch.get("reserved"):
        return True
    with store.lock:
        current = store.audit(id)["reserved"]
        if "reservation_before" not in batch:
            batch["reservation_before"] = current
            _save_state(store, id, state)
        cost = round(len(batch["employer_keys"])*0.1, 2)
        if current + 1e-8 < batch["reservation_before"] + cost:
            if not store.reserve(id, cost):
                batch.update(phase="budget_blocked", error="Employer TinySet research exceeds the remaining paid cap.")
                _save_state(store, id, state)
                return False
        batch.update(reserved=True, cost=cost, phase="reserved")
        _save_state(store, id, state)
        return True


def _tinyset_context(engine, id, employers, client, stop):
    store = engine.store
    state = _state(store, id)
    if not state:
        keys = sorted(employers)
        state = {"version": JOB_RULE_VERSION, "created_at": utcnow(), "employers": {}, "batches": []}
        for number, start in enumerate(range(0, len(keys), 25), 1):
            state["batches"].append({"number": number, "name": f"Zombie Check {id} job employers {number}",
                                     "employer_keys": keys[start:start+25], "phase": "planned"})
        _save_state(store, id, state)
    expected = {key for batch in state.get("batches", []) for key in batch["employer_keys"]}
    if expected != set(employers):
        raise ValueError("Saved employer manifest differs from original input; keep the same audit/input for resume.")
    store.event(id, "phase", f"TinySet researches {len(employers)} unique employers; job availability/intake remain separate per-posting checks.")
    for batch in state["batches"]:
        if stop.is_set():
            return state
        if batch.get("phase") == "done":
            continue
        if not _reserve_batch(store, id, state, batch):
            continue
        dataset_id = batch.get("dataset_id")
        if not dataset_id and batch["phase"] in ("creating", "uncertain", "recovery_required"):
            recovered = client.find_dataset(batch["name"])
            if not recovered:
                batch.update(phase="recovery_required", error="Remote creation outcome uncertain; no duplicate dataset was created.")
                _save_state(store, id, state)
                store.event(id, "recovery", batch["error"])
                continue
            dataset_id = recovered.get("id") or recovered.get("dataset_id")
            batch.update(dataset_id=dataset_id, phase="running")
            _save_state(store, id, state)
        if not dataset_id:
            entities = [{"name": employers[key]["employer"], "website": employers[key]["employer_website"]}
                        for key in batch["employer_keys"]]
            batch.update(phase="creating", attempts=batch.get("attempts", 0)+1)
            _save_state(store, id, state)
            try:
                created = client.create_dataset(batch["name"], entities)
                dataset_id = created.get("id") or created.get("dataset_id")
                if not dataset_id:
                    raise APIError(0, "TinySet did not return a dataset ID", ambiguous=True)
                batch.update(dataset_id=dataset_id, phase="running", error=None)
                _save_state(store, id, state)
            except APIError as error:
                batch.update(phase="uncertain" if error.ambiguous else "retryable" if error.status in (429, 503) else "failed", error=str(error))
                _save_state(store, id, state)
                store.event(id, "tinyset_error", str(error))
                if error.status == 402:
                    stop.set()
                continue
        deadline = time.monotonic()+45*60
        remote = None
        while not stop.is_set():
            if time.monotonic() >= deadline:
                store.event(id, "remote_wait", "Employer TinySet run still pending; remote ID is saved for resume.")
                stop.set()
                break
            remote = client.dataset(dataset_id)
            batch["run_id"] = (remote.get("run") or {}).get("id")
            _save_state(store, id, state)
            if remote.get("status") in ("ready", "failed", "cancelled"):
                break
            if stop.wait(12):
                break
        if stop.is_set():
            return state
        returned = client.dataset_rows(dataset_id)
        for remote_row in returned:
            raw = remote_row.get("data") or {}
            name = raw.get("company") or raw.get("row_id") or ""
            website = safe_url(raw.get("website"))
            matches = [key for key in batch["employer_keys"] if _name(name)==_name(employers[key]["employer"])
                       and website and host(website)==host(employers[key]["employer_website"])]
            if len(matches) != 1:
                store.event(id, "reconcile", "Rejected unmatched employer TinySet row: "+str(name)[:120])
                continue
            key = matches[0]
            if key in state["employers"] and state["employers"][key].get("raw"):
                continue
            state["employers"][key] = {"raw": raw, "dataset_id": dataset_id, "matched_at": utcnow(), "verified": True}
        matched = sum(bool(state["employers"].get(key, {}).get("verified") and state["employers"].get(key, {}).get("raw"))
                      for key in batch["employer_keys"])
        batch.update(phase="done" if matched==len(batch["employer_keys"]) else "partial",
                     matched=matched, remote_status=remote.get("status") if remote else "unknown")
        _save_state(store, id, state)
        store.event(id, "tinyset", f"Employer dataset matched {matched}/{len(batch['employer_keys'])} exact name/domain identities.")
    return state


def _candidate(value):
    obj = as_object(value)
    return safe_url(obj.get("url") if obj else value)


def _drill_linked_source(engine, id, client, kind, website, index_entry, signal, linked, stop):
    """Check up to three actual linked date sources, never invented URLs."""
    if kind not in ("blog", "release") or signal.get("latest_date") or not index_entry.get("page"):
        return signal
    index = index_entry["page"]
    index_url = index.get("final_url") or signal.get("url")
    excluded = {"ai", "engineering", "about", "about-us", "careers", "contact", "contact-us", "privacy", "privacy-policy",
                "terms", "terms-of-service", "login", "signup", "register", "archive", "archives", "all", "feed", "rss"}
    candidates = []
    for value in index.get("links") or []:
        candidate = safe_url(value)
        parsed = urlparse(candidate)
        path = parsed.path.rstrip("/").lower()
        if (not candidate or not related_host(candidate, website) or not path
            or _url_identity(candidate)==_url_identity(index_url or "")
            or re.search(r"/(?:search|tags?|topics?|categor(?:y|ies)|index)(?:/|\.|$)", path)
            or path.split("/")[-1] in excluded
            or any(key in ("q", "search", "tag", "topic", "page") for key, _ in parse_qsl(parsed.query))):
            continue
        if kind=="blog":
            if not (re.search(r"/(?:blog|news|newsroom|articles?|posts?)/", path) or host(candidate).startswith("blog.")):
                continue
        elif not re.search(r"changelog|release[-_/]?notes|/releases?(?:/|$)|/updates?(?:/|$)|/whats-new(?:/|$)", path):
            continue
        if not any(_url_identity(candidate)==_url_identity(previous) for previous in candidates):
            candidates.append(candidate)
    checked = []
    for candidate in candidates[:3]:
        if stop.is_set():
            break
        entry = engine.fetched(id, client, [candidate]).get(candidate, {})
        page = entry.get("page") or {}
        observed = observe_page(kind, candidate, page=entry.get("page"), error=entry.get("error"),
                                linked=True, company_url=website)
        checked.append({"url": candidate, "final_url": page.get("final_url"), "checked_at": page.get("checked_at") or entry.get("checked_at") or utcnow(),
                        "verified": observed.get("verified"), "latest_date": observed.get("latest_date"), "error": observed.get("error")})
        if observed.get("verified") and observed.get("latest_date"):
            observed.update(shared=True, scope="employer", employer=signal.get("employer"), employer_website=website,
                            method="tinyset+tinyfetch", drilled_from=index_url, source_index_url=index_url,
                            drill_checks=checked, checked_at=page.get("checked_at") or observed.get("checked_at"))
            return observed
    signal = copy.deepcopy(signal)
    signal["drill_checks"] = checked
    return signal


def _context_signals(engine, id, employers, state, client, stop, refresh=False):
    contexts = {}
    for key, employer in employers.items():
        if stop.is_set():
            break
        saved = state.get("employers", {}).get(key, {})
        if saved.get("signals") and not refresh:
            contexts[key] = saved
            continue
        website = employer["employer_website"]
        home_entry = engine.fetched(id, client, [website]).get(website, {})
        home = home_entry.get("page") or {}
        urls = discover_signal_urls(home, home.get("final_url") or website)
        linked = set(home.get("links") or [])
        for kind in SHARED:
            candidate = _candidate((saved.get("raw") or {}).get(kind))
            previous = (saved.get("signals") or {}).get(kind) or {}
            proven = safe_url(previous.get("url")) if previous.get("verified") else ""
            # Keep an already verified Search-resolved source when the raw
            # TinySet field was missing or pointed somewhere else. Recheck its
            # date with the current rules without repeating discovery.
            if refresh and proven and (not candidate or _url_identity(proven)!=_url_identity(candidate)):
                candidate = proven
            if candidate:
                urls[kind] = candidate
        entries = engine.fetched(id, client, [urls[kind] for kind in SHARED])
        signals = {}
        for kind in SHARED:
            entry = entries.get(urls[kind], {})
            signal = observe_page(kind, urls[kind], page=entry.get("page"), error=entry.get("error"),
                                  linked=urls[kind] in linked, company_url=website)
            signal.update(shared=True, scope="employer", employer=employer["employer"], employer_website=website,
                          method="tinyset+tinyfetch" if saved.get("verified") else "tinyfetch")
            previous = (saved.get("signals") or {}).get(kind) or {}
            if refresh and previous.get("verified") and _url_identity(previous.get("url") or "")==_url_identity(urls[kind]):
                for provenance_key in ("discovered_by", "discovery_query", "drilled_from", "source_index_url", "drill_checks"):
                    if provenance_key in previous:
                        signal[provenance_key] = copy.deepcopy(previous[provenance_key])
                if previous.get("discovered_by")=="tinysearch":
                    signal["method"] = "tinyset+tinysearch+tinyfetch"
            if entry.get("page", {}).get("checked_at"):
                signal["checked_at"] = entry["page"]["checked_at"]
            elif entry.get("checked_at"):
                signal["checked_at"] = entry["checked_at"]
            signal = _drill_linked_source(engine, id, client, kind, website, entry, signal, linked, stop)
            # Search only missing or unowned context sources. Existing verified
            # TinySet facts do not trigger speculative extra endpoint usage.
            needs_discovery = signal.get("error") in ("page_not_found", "unverified_source_identity")
            if needs_discovery and hasattr(client, "search") and not stop.is_set():
                term = {"blog": "official blog news", "release": "official changelog release notes", "social": "official social GitHub"}[kind]
                query = f"{employer['employer']} {host(website)} {term}"
                try:
                    found = client.search(query)
                    candidates = []
                    for result in found.get("results", []):
                        candidate_url = safe_url(result.get("url"))
                        if not candidate_url or candidate_url == urls[kind]:
                            continue
                        if kind in ("blog", "release"):
                            pattern = r"/(?:blog|news|newsroom|articles)(?:/|$)" if kind=="blog" else r"changelog|release[-_/ ]?notes|/releases(?:/|$)|/updates(?:/|$)"
                            if related_host(candidate_url, website) and re.search(pattern, candidate_url, re.I):
                                candidates.append(candidate_url)
                        elif candidate_url in linked and re.search(r"github\.com|linkedin\.com|x\.com|twitter\.com", candidate_url):
                            candidates.append(candidate_url)
                    if candidates:
                        discovered_url = candidates[0]
                        discovered = engine.fetched(id, client, [discovered_url]).get(discovered_url, {})
                        replacement = observe_page(kind, discovered_url, page=discovered.get("page"), error=discovered.get("error"),
                                                   linked=discovered_url in linked, company_url=website)
                        if replacement.get("verified") or not replacement.get("error"):
                            replacement.update(shared=True, scope="employer", employer=employer["employer"], employer_website=website,
                                               method="tinyset+tinysearch+tinyfetch", discovered_by="tinysearch", discovery_query=query)
                            replacement["checked_at"] = (discovered.get("page") or {}).get("checked_at") or discovered.get("checked_at") or replacement["checked_at"]
                            signal = replacement
                    engine.store.event(id, "context_search", f"{employer['employer']}: searched for a missing/uncertain official {kind} source.")
                except APIError as error:
                    engine.store.event(id, "context_search_error", str(error))
                    if error.status==402:
                        stop.set()
            signals[kind] = signal
        saved.update(signals=signals, context_checked_at=utcnow())
        state.setdefault("employers", {})[key] = saved
        contexts[key] = saved
        _save_state(engine.store, id, state)
    return contexts


def refresh_job_context(engine, audit_id):
    """Enhance shared sources without new datasets or rechecking any role.

    Only employer blog/release/social records, coverage counters, and their
    evidence links change. Posting verdict, intake, identity, role timestamps,
    original cells and row status remain as previously independently checked.
    """
    id, store, client = audit_id, engine.store, engine.client_factory(audit_id)
    audit = store.audit(id)
    if audit["config"].get("mode") != "jobs":
        raise ValueError("Shared context refresh requires a saved jobs-mode audit.")
    state = _state(store, id)
    if not state or not state.get("employers") or any(not item.get("verified") or not item.get("raw") for item in state["employers"].values()):
        raise ValueError("Refresh requires existing matched TinySet employer raw/IDs; it will not create a dataset.")
    rows = store.rows(id)
    employers, values_by_row = {}, {}
    for row in rows:
        values = _read_fields(audit, row)
        values_by_row[row["row_id"]] = values
        employers.setdefault(values["employer_key"], values)
    import threading
    contexts = _context_signals(engine, id, employers, state, client, threading.Event(), refresh=True)
    updated, core_unchanged = 0, True
    distribution = {}
    for row in rows:
        result = copy.deepcopy(row.get("result") or {})
        if not result:
            continue
        before = {key: copy.deepcopy(value) for key, value in result.items() if key not in ("signals", "signals_checked", "signals_verified", "evidence_links")}
        job_signals = {kind: copy.deepcopy(result.get("signals", {}).get(kind)) for kind in ("jobs", "signup")}
        context = contexts[values_by_row[row["row_id"]]["employer_key"]]
        for kind in SHARED:
            result.setdefault("signals", {})[kind] = copy.deepcopy(context["signals"][kind])
        result["signals_checked"] = sum(bool(s.get("checked_at") and s.get("url")) for s in result["signals"].values())
        result["signals_verified"] = sum(bool(s.get("verified")) for s in result["signals"].values())
        links = [s["url"] for s in result["signals"].values() if s.get("url")]
        links += [s.get("source_index_url") for s in result["signals"].values() if s.get("source_index_url")]
        board = result.get("board_check") or {}
        links += [board.get("url"), board.get("metadata_url"), result.get("identity", {}).get("canonical_url")]
        result["evidence_links"] = list(dict.fromkeys(value for value in links if value))
        after = {key: value for key, value in result.items() if key not in ("signals", "signals_checked", "signals_verified", "evidence_links")}
        intact = before==after and all(job_signals[kind]==result["signals"].get(kind) for kind in ("jobs", "signup"))
        core_unchanged = core_unchanged and intact
        if not intact:
            raise ValueError("Context enhancement unexpectedly changed original posting evidence.")
        store.row_update(id, row["row_id"], result=result)
        updated += 1
        distribution[result["signals_verified"]] = distribution.get(result["signals_verified"], 0)+1
    store.event(id, "context_refresh", f"Enhanced shared employer evidence for {updated} original rows; role/intake/verdicts/dates preserved, no new datasets or role fetches.")
    return {"audit_id": id, "updated_at": utcnow(), "rows_enhanced": updated, "job_core_unchanged": core_unchanged,
            "new_datasets": 0, "role_api_fetches": 0, "verified_signal_distribution": distribution,
            "employers": {key: {"dataset_id": item.get("dataset_id"), "signals": item.get("signals")} for key, item in contexts.items()}}


def _board_data(engine, id, values, client):
    entries = engine.fetched(id, client, [values["source_url"], values["metadata_url"]])
    listing, listing_error = parse_json_page(entries.get(values["source_url"]))
    metadata, metadata_error = parse_json_page(entries.get(values["metadata_url"]))
    board = {"url": values["source_url"], "metadata_url": values["metadata_url"], "checked_at": utcnow(),
             "complete": False, "ids": set(), "error": listing_error or metadata_error, "metadata_name": None}
    if not listing or not isinstance(listing.get("jobs"), list) or not metadata:
        return board
    board["metadata_name"] = metadata.get("name")
    if _name(metadata.get("name")) != _name(values["employer"]):
        board["error"] = {"error": "employer_board_mismatch"}
        return board
    jobs = listing["jobs"]
    ids = {str(job.get("id")) for job in jobs if isinstance(job, dict) and str(job.get("id", "")).isdigit()}
    total = (listing.get("meta") or {}).get("total")
    if len(ids) != len(jobs) or (total is not None and (not isinstance(total, int) or total!=len(jobs))):
        board["error"] = {"error": "incomplete_or_invalid_board_feed"}
        return board
    board.update(complete=True, ids=ids, error=None)
    page = entries.get(values["source_url"], {}).get("page") or {}
    board["checked_at"] = page.get("checked_at") or board["checked_at"]
    return board


def _role_date(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        if parsed.astimezone(dt.timezone.utc) > dt.datetime.now(dt.timezone.utc) or parsed.year < 1990:
            return None
        return parsed
    except ValueError:
        return None


def _base_result(values, context):
    signals = copy.deepcopy(context.get("signals", {}))
    for kind in ("jobs", "signup"):
        signals[kind] = {"kind": kind, "status": "unknown", "url": values["job_api_url"], "quote": "", "note": "Pending exact posting check.",
                         "checked_at": None, "verified": False, "date_verified": False, "latest_date": None,
                         "method": "tinyfetch", "scope": "job", "shared": False, "error": None}
    return {"verdict": "", "confidence": "insufficient", "review_required": True, "reason": "Exact job evidence needs review.",
            "latest_activity_date": None, "signals": signals, "checked_at": utcnow(), "rule_version": JOB_RULE_VERSION,
            "identity": {"status": "ambiguous", "canonical_url": values["job_url"], "url": values["job_api_url"],
                         "verified": False, "current_name": values["title"], "scope": "job_post"},
            "job_first_published": None, "job_updated_at": None, "current_job_title": None,
            "tinyset_employer_verified": bool(context.get("verified")), "employer": values["employer"],
            "employer_name": values["employer"], "employer_website": values["employer_website"],
            "tinyset_scope": "Shared employer blog/release/social context; posting identity and intake checked independently"}


def _source_excerpt(page, field, length=400):
    """A literal slice of the fetched JSON, not generated source quotation."""
    text = str((page or {}).get("text") or "")
    match = re.search(r'"'+re.escape(field)+r'"\s*:', text)
    return text[match.start():match.start()+length] if match else ""


def _closed_notice(text):
    return re.search(r"(?:\b(?:this|the) (?:job|position|role)(?: posting)? (?:is (?:closed|no longer available)|has been (?:closed|filled|removed))\b|\bno longer accepting applications\b|\bthis job is no longer accepting\b)", str(text or "")[:2500], re.I)


def _contains_posting_id(url, posting_id):
    parsed = urlparse(url)
    return bool(re.search(r"(?<!\d)"+re.escape(posting_id)+r"(?!\d)", parsed.path)
                or any(key in ("gh_jid", "job_id", "id") and value==posting_id for key, value in parse_qsl(parsed.query)))


def _page_matches(page, expected_url, posting_id, title):
    final = safe_url((page or {}).get("final_url") or expected_url)
    text = normalized(str((page or {}).get("text") or "")+" "+str((page or {}).get("title") or ""))
    return bool(page and final and _url_identity(final, posting_id)==_url_identity(expected_url, posting_id)
                and _contains_posting_id(final, posting_id) and _name(title) in _name(text))


def _localized_page(engine, id, values, role, public_entry, role_entry, client, stop):
    """Resolve a missing default route from verified job-language metadata only."""
    language = str(role.get("language") or "").strip().replace("_", "-")
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
        return {"language": None, "attempts": [], "resolved": False}, None, None
    parsed = urlparse(values["job_url"])
    labels = list(dict.fromkeys((language.lower(), language.split("-")[0].lower())))
    candidates = []
    # Prefer an actual same-site language link for this posting where a page,
    # board or employer homepage already exposed one during this audit.
    links = list((public_entry.get("page") or {}).get("links") or [])+list((role_entry.get("page") or {}).get("links") or [])
    for source_url in (values.get("board_url"), values.get("employer_website")):
        snapshot = engine.store.snapshot(id, source_url) if source_url else None
        links += list(((snapshot or {}).get("page") or {}).get("links") or [])
    for candidate in links:
        candidate = safe_url(candidate)
        candidate_parts = urlparse(candidate)
        locale = candidate_parts.path.strip("/").split("/", 1)[0].lower()
        locale_match = locale in labels or any(key in ("lang", "locale", "language") and value.lower().replace("_", "-") in labels
                                              for key, value in parse_qsl(candidate_parts.query))
        if (candidate and candidate_parts.hostname==parsed.hostname and locale_match
            and _contains_posting_id(candidate, values["posting_id"])):
            candidates.append(candidate)
    # Prefix the metadata language onto the default route. If the route
    # already has a locale, replace it rather than guessing multiple nests.
    path = parsed.path
    parts = path.lstrip("/").split("/", 1)
    if len(parts)>1 and re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", parts[0], re.I):
        path = "/"+parts[1]
    for label in labels:
        candidate = urlunparse(parsed._replace(path="/"+label+(path if path.startswith("/") else "/"+path), fragment=""))
        if candidate!=values["job_url"]:
            candidates.append(candidate)
    trace = {"language": language, "attempts": [], "resolved": False,
             "note": "Alternate locale comes from the exact verified posting's language metadata; original default-page evidence is retained."}
    for candidate in list(dict.fromkeys(candidates))[:2]:
        if stop.is_set():
            break
        entry = engine.fetched(id, client, [candidate]).get(candidate, {})
        page, error = entry.get("page") or {}, entry.get("error") or {}
        final = safe_url(page.get("final_url") or candidate)
        match = bool(urlparse(final).hostname==parsed.hostname
                     and _page_matches(page, candidate, values["posting_id"], role["title"])
                     and not _closed_notice(page.get("text")))
        observed = {"url": candidate, "final_url": final, "checked_at": page.get("checked_at") or entry.get("checked_at") or utcnow(),
                    "error": error.get("error"), "http_status": error.get("status"), "matched_posting": match}
        trace["attempts"].append(observed)
        if match:
            trace.update(resolved=True, source_url=candidate, final_url=final, checked_at=observed["checked_at"],
                         title=str(role["title"]), posting_id=values["posting_id"])
            return trace, page, candidate
    # Some published ATS records carry the wrong language value. Discover an
    # actual indexed route rather than trying unsourced locale permutations.
    if hasattr(client, "search") and not stop.is_set():
        queries = [f"{values['employer']} {values['posting_id']} {role['title']}"]
        location = str((role.get("location") or {}).get("name") or "").strip()
        if location:
            queries.append(f"{values['employer']} {role['title']} {location}")
        trace["source_discovery"] = []
        for query in queries:
            if stop.is_set():
                break
            try:
                found = client.search(query)
                discovery = {"query": query, "checked_at": utcnow(), "candidate_urls": []}
                trace["source_discovery"].append(discovery)
                for item in found.get("results", []):
                    candidate = safe_url(item.get("url"))
                    candidate_parts = urlparse(candidate)
                    if (not candidate or candidate_parts.hostname!=parsed.hostname
                        or values["posting_id"] not in candidate_parts.path.strip("/").split("/")
                        or any(key=="gh_jid" and value!=values["posting_id"] for key, value in parse_qsl(candidate_parts.query))):
                        continue
                    if candidate in discovery["candidate_urls"]:
                        continue
                    discovery["candidate_urls"].append(candidate)
                    entry = engine.fetched(id, client, [candidate]).get(candidate, {})
                    page, error = entry.get("page") or {}, entry.get("error") or {}
                    final = safe_url(page.get("final_url") or candidate)
                    match = bool(urlparse(final).hostname==parsed.hostname
                                 and _page_matches(page, candidate, values["posting_id"], role["title"])
                                 and not _closed_notice(page.get("text")))
                    observed = {"url": candidate, "final_url": final, "checked_at": page.get("checked_at") or entry.get("checked_at") or utcnow(),
                                "error": error.get("error"), "http_status": error.get("status"), "matched_posting": match,
                                "discovered_by": "tinysearch", "discovery_query": query}
                    trace["attempts"].append(observed)
                    if match:
                        prefix = candidate_parts.path.strip("/").split("/", 1)[0]
                        source_language = page.get("language") or (prefix if re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", prefix) else language)
                        trace.update(resolved=True, source_url=candidate, final_url=final, checked_at=observed["checked_at"],
                                     title=str(role["title"]), posting_id=values["posting_id"], metadata_language=language,
                                     language=source_language, discovered_by="tinysearch", discovery_query=query,
                                     note="A searched official route matched the exact posting, title and original site despite unavailable or inconsistent default-language routing. Original missing-route evidence is retained.")
                        return trace, page, candidate
                    if len(discovery["candidate_urls"])>=2:
                        break
            except APIError as error:
                trace.setdefault("discovery_errors", []).append({"query": query, "error": str(error)})
                if error.status==402:
                    stop.set()
                    break
    return trace, None, None


def _finish_result(result, board):
    signals = result["signals"]
    result["signals_checked"] = sum(bool(s.get("checked_at") and s.get("url")) for s in signals.values())
    result["signals_verified"] = sum(bool(s.get("verified")) for s in signals.values())
    result["evidence_links"] = list(dict.fromkeys([s["url"] for s in signals.values() if s.get("url")]
        + [board["url"], board["metadata_url"], result["identity"]["canonical_url"]]))
    result["board_check"] = {k: v for k, v in board.items() if k != "ids"}
    if result["signals_checked"] < 4 or not result.get("tinyset_employer_verified"):
        result.update(review_required=True, reason=result["reason"]+" Employer TinySet context or four completed signal checks are still incomplete.")
    return result


def _job_row(engine, id, row, values, board, context, client, stop):
    if stop.is_set():
        return
    store = engine.store
    store.row_update(id, row["row_id"], status="checking", error=None)
    entries = engine.fetched(id, client, [values["job_api_url"], values["job_url"]])
    role_entry = entries.get(values["job_api_url"], {})
    role, error = parse_json_page(role_entry)
    result = _base_result(values, context)
    stamp = (role_entry.get("page") or {}).get("checked_at") or role_entry.get("checked_at") or utcnow()
    for kind in ("jobs", "signup"):
        result["signals"][kind]["checked_at"] = stamp
        result["signals"][kind]["quote_format"] = "extracted_fields"
    jobs, intake = result["signals"]["jobs"], result["signals"]["signup"]
    public_entry = entries.get(values["job_url"], {})
    public_page = public_entry.get("page") or {}
    public_error = public_entry.get("error") or {}
    public_text = str(public_page.get("text") or "")
    closed_notice = _closed_notice(public_text)
    public_terminal = public_error.get("error")=="page_not_found" and public_error.get("status") in (404, 410)
    result["public_page_check"] = {"url": values["job_url"], "final_url": safe_url(public_page.get("final_url")) or None,
        "checked_at": public_page.get("checked_at") or public_entry.get("checked_at") or utcnow(),
        "available": bool(public_page and public_text.strip()), "error": public_error.get("error"),
        "http_status": public_error.get("status"), "terminal_missing": bool(public_terminal),
        "explicit_closed_notice": closed_notice.group(0) if closed_notice else None,
        "verified_ui": False,
        "note": "Public page availability is recorded separately from the ATS intake configuration; blocks/timeouts do not establish death."}
    summary = {"posting_id": values["posting_id"], "provider": "greenhouse", "board_token": values["token"]}
    if not board["complete"]:
        result["reason"] = "Official employer board was unavailable, incomplete, or did not match the supplied employer."
        jobs["error"] = (board.get("error") or {}).get("error", "incomplete_board")
    elif error:
        code, status = error.get("error"), error.get("status")
        jobs.update(error=code, status="not_found" if code=="page_not_found" else "blocked" if code in ("bot_blocked", "login_required") else "unknown",
                    note="Exact posting API returned "+str(code))
        intake.update(error=code, status=jobs["status"], note="Application-question endpoint for this exact posting was checked; no intake could be read.")
        if code=="page_not_found" and status in (404, 410) and values["posting_id"] not in board["ids"]:
            result.update(verdict="zombie", confidence="medium", review_required=False,
                          reason="Exact posting is absent from a complete healthy employer board and its detail returns 404/410. This describes a dead public posting, not a dead employer.")
            jobs.update(verified=True, quote="", absence_evidence={"posting_id": values["posting_id"],
                "complete_board_count": len(board["ids"]), "detail_http_status": status, "board_checked_at": board["checked_at"]})
            intake.update(verified=True)
            result["identity"].update(status="same", verified=True)
        else:
            result["reason"] = "The posting could not be verified; blocking and transient failures are not evidence of a ghost job."
    else:
        api_url = safe_url(role.get("absolute_url"))
        valid = str(role.get("id"))==values["posting_id"] and _name(role.get("company_name"))==_name(values["employer"])
        valid = valid and api_url and _url_identity(api_url, values["posting_id"])==_url_identity(values["job_url"], values["posting_id"]) and bool(role.get("title"))
        if not valid:
            jobs["error"] = "posting_identity_mismatch"
            result["reason"] = "Live role ID, employer, title presence or canonical job URL does not match this original posting."
        elif values["posting_id"] not in board["ids"]:
            jobs["error"] = "board_detail_conflict"
            result["reason"] = "Detail exists but the posting is absent from the complete public board; visibility/availability requires review."
        else:
            locale_trace, localized_page, localized_url = {}, None, None
            if public_terminal and not closed_notice and not stop.is_set():
                locale_trace, localized_page, localized_url = _localized_page(engine, id, values, role, public_entry, role_entry, client, stop)
                result["public_page_check"]["localized_resolution"] = locale_trace
                result["public_page_check"]["resolved_by_locale"] = bool(locale_trace.get("resolved"))
            first, updated = _role_date(role.get("first_published")), _role_date(role.get("updated_at"))
            result.update(job_first_published=first.isoformat() if first else None,
                          job_updated_at=updated.isoformat() if updated else None, current_job_title=str(role["title"]))
            result["latest_activity_date"] = updated.date().isoformat() if updated else None
            result["identity"].update(status="same", verified=True, canonical_url=api_url, current_name=str(role["title"]))
            if locale_trace.get("resolved"):
                result["identity"].update(canonical_url=locale_trace["final_url"], locale_language=locale_trace["language"],
                                          note="Verified localized page resolves the missing default route for the same exact posting.")
            jobs.update(status="active", verified=True, latest_date=result["latest_activity_date"], date_verified=bool(updated),
                        quote=json.dumps({key:role.get(key) for key in ('id','company_name','title','absolute_url','first_published','updated_at')},ensure_ascii=False),
                        note="Exact public ATS posting ID, employer and URL match; role is present in the complete official board. Updated timestamp is an administrative posting update, not proof of new hiring intent.")
            questions = role.get("questions")
            fields = [field for q in questions if isinstance(q, dict) for field in (q.get("fields") or []) if isinstance(field, dict)] if isinstance(questions, list) else []
            configured = any(field.get("type") in ("input_text", "input_file", "textarea", "multi_value_single_select", "multi_value_multi_select") for field in fields)
            labels = [str(q.get("label") or "") for q in (questions or []) if isinstance(q, dict)] if isinstance(questions, list) else []
            intake.update(status="active" if configured else "unknown", verified=configured,
                          quote=json.dumps({'posting_id':role.get('id'),'question_count':len(labels),'question_labels':labels[:8],'field_types':sorted(set(str(f.get('type','')) for f in fields))},ensure_ascii=False),
                          note="Public application question definitions are configured for this exact role. No application was submitted; rendered form operability, backend acceptance and genuine vacancy intent are unverified.",
                          observation_scope="ATS question configuration only", error=None if configured else "intake_not_configured")
            rendered = localized_page or (entries.get(values["job_url"], {}) or {}).get("page") or {}
            rendered_source = localized_url or values["job_url"]
            rendered_text = str(rendered.get("text") or "")
            rendered_url = safe_url(rendered.get("final_url") or rendered_source)
            page_matches = _page_matches(rendered, rendered_source, values["posting_id"], role["title"])
            form_text = (page_matches and re.search(r"\bfirst\s*name\b", rendered_text, re.I)
                         and re.search(r"\blast\s*name\b", rendered_text, re.I)
                         and re.search(r"\bemail\b", rendered_text, re.I)
                         and re.search(r"\b(?:resume|cv|apply|submit application)\b", rendered_text, re.I))
            result["job_page_check"] = {"url": rendered_source, "final_url": rendered_url,
                "checked_at": rendered.get("checked_at") or utcnow(), "matched_posting": page_matches,
                "application_form_text_found": bool(form_text),
                "error": None if localized_page else (entries.get(values["job_url"], {}).get("error") or {}).get("error")}
            result["public_page_check"].update(matched_posting=page_matches, application_form_text_found=bool(form_text))
            if configured and form_text:
                intake.update(url=rendered_url, checked_at=rendered.get("checked_at") or stamp,
                    quote=short_quote(rendered_text, r"first\s*name|last\s*name|submit application"),
                    note="The exact job page returns application form labels and the ATS exposes configured questions. No form was submitted; enabled controls, backend acceptance and genuine vacancy intent are unverified.",
                    observation_scope="Rendered form text and ATS question configuration")
            summary.update(id=role["id"], company_name=role["company_name"], title=role["title"], absolute_url=api_url,
                           first_published=role.get("first_published"), updated_at=role.get("updated_at"), question_count=len(labels),
                           question_labels=labels[:8], intake_configured=configured)
            if configured:
                age = (dt.datetime.now(dt.timezone.utc)-first.astimezone(dt.timezone.utc)).days if first else None
                result["job_age_days"] = age
                result.update(verdict="slowing down" if age is not None and age>90 else "alive", confidence="medium", review_required=False)
                result["reason"] = (f"Public posting and intake schema remain available, but the verified role was first published {age} days ago (>90-day caution heuristic). Age alone does not prove a ghost vacancy."
                                    if age is not None and age>90 else "Exact public posting and its intake schema are available. This establishes posting health; funded headcount, recruiter response and successful application submission are unverified.")
                if normalized(role['title']) != normalized(values['title']):
                    result["reason"] += " The same posting ID now has a changed title; original title is retained."
            else:
                result["reason"] = "The exact posting is public, but a configured application intake could not be established."
            if (public_terminal and not locale_trace.get("resolved")) or closed_notice:
                result.update(verdict="", confidence="insufficient", review_required=True,
                    reason="The official detail/intake remains configured, but its public job page is missing or explicitly closed. This source conflict needs review before assigning a posting-health verdict.")
            elif locale_trace.get("resolved"):
                result["reason"] += (" The default public route returned 404/410; an actual searched official route matched the same exact posting despite inconsistent language metadata. Original missing-route evidence is retained."
                                     if locale_trace.get("discovered_by")=="tinysearch" else " The default public route returned 404/410; a same-site page in the posting's verified metadata language matched the exact role. Original missing-route evidence is retained.")
    result = _finish_result(result, board)
    status = "done" if result["verdict"] and not result["review_required"] else "review"
    store.row_update(id, row["row_id"], raw=summary, result=result, dataset_id=context.get("dataset_id"), status=status,
                     error=jobs.get("error") or intake.get("error"))
    store.event(id, "row", f"{row['row_id']} · {values['employer']} · {result['verdict'] or 'needs evidence'} · exact posting check")


def run_jobs(engine, audit_id, stop):
    """Run under Engine's existing worker lease; preserve every original row."""
    id, store, client = audit_id, engine.store, engine.client_factory(audit_id)
    audit = store.audit(id)
    store.execute("UPDATE rows SET status='pending' WHERE audit_id=? AND status='checking'", (id,))
    all_rows = store.rows(id)
    valid, employers, boards = {}, {}, {}
    for row in all_rows:
        try:
            values = _read_fields(audit, row)
            valid[row["row_id"]] = values
            employers.setdefault(values["employer_key"], values)
        except ValueError as error:
            if row["status"] != "done":
                store.row_update(id, row["row_id"], status="review", error=str(error), result={"verdict": "", "confidence": "insufficient",
                    "reason": str(error), "review_required": True, "signals": {}, "signals_checked": 0, "signals_verified": 0,
                    "evidence_links": [], "checked_at": utcnow(), "rule_version": JOB_RULE_VERSION})
    if not valid:
        store.set_status(id, "needs_review", "No valid supported public posting identities.")
        return
    state = _tinyset_context(engine, id, employers, client, stop)
    if stop.is_set():
        store.set_status(id, "paused")
        return
    contexts = _context_signals(engine, id, employers, state, client, stop)
    for values in valid.values():
        if stop.is_set():
            break
        if values["source_url"] not in boards:
            boards[values["source_url"]] = _board_data(engine, id, values, client)
            board = boards[values["source_url"]]
            store.event(id, "board", f"{values['employer']}: {len(board['ids'])} postings in complete official feed." if board["complete"] else f"{values['employer']}: board source needs review.")
    if stop.is_set():
        store.set_status(id, "paused")
        return
    pending = [row for row in store.rows(id) if row["row_id"] in valid and row["status"] != "done"]
    store.event(id, "phase", f"Independently checking {len(pending)} exact role APIs and public job pages with at most six workers.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tasks = {pool.submit(_job_row, engine, id, row, valid[row["row_id"]], boards[valid[row["row_id"]]["source_url"]],
                            contexts.get(valid[row["row_id"]]["employer_key"], {}), client, stop): row for row in pending}
        for task in concurrent.futures.as_completed(tasks):
            row = tasks[task]
            try:
                task.result()
            except Exception as error:
                store.row_update(id, row["row_id"], status="review", error=str(error))
                store.event(id, "job_error", row["row_id"]+": "+str(error))
                if isinstance(error, APIError) and error.status==402:
                    stop.set()
    if stop.is_set():
        store.set_status(id, "paused")
        return
    finished = store.audit(id)
    complete = finished["counts"].get("done", 0)==finished["total"]
    store.set_status(id, "complete" if complete else "needs_review")
    store.event(id, "finish", "Every original posting has a source-backed posting-health verdict; genuine vacancy intent remains unverified."
                if complete else "Job evidence saved; unresolved posting/context checks remain. This is not full completion.")

