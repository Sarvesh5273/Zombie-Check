import csv
import hashlib
import io
import json
from .models import safe_url


JOB_COLUMN_ALIASES = {
    'employer': ('employer', 'company', 'company name', 'organization'),
    'title': ('title', 'job title', 'role', 'position'),
    'job_url': ('job url', 'posting url', 'job posting url', 'application url'),
    'job_id': ('job id', 'posting id', 'greenhouse id'),
    'employer_website': ('employer website', 'company website', 'employer domain', 'company domain', 'website'),
    'board_token': ('board token', 'greenhouse token', 'ats token'),
    'board_url': ('board url', 'careers url'),
    'job_api_url': ('job api url', 'posting api url'),
    'source_url': ('source url', 'feed url'),
}


def job_column_mapping(headers, supplied=None):
    """Suggest mappings and validate explicit user column selections."""
    lower = [str(h).strip().casefold().replace('_', ' ') for h in headers]
    result = {field: next(i for i,h in enumerate(lower) if h in aliases)
              for field,aliases in JOB_COLUMN_ALIASES.items() if any(h in aliases for h in lower)}
    if supplied is not None:
        if not isinstance(supplied,dict) or not supplied.keys() <= JOB_COLUMN_ALIASES.keys():
            raise ValueError('Unknown job column mapping')
        for field,value in supplied.items():
            if value is None or value == '':
                result.pop(field,None)
                continue
            if isinstance(value,str) and value in headers:
                value = headers.index(value)
            if isinstance(value,bool) or not isinstance(value,int) or not 0 <= value < len(headers):
                raise ValueError('Select a valid column for '+field)
            result[field] = value
    return result


def parse_csv(content):
    if len(content.encode("utf-8")) > 20 * 1024 * 1024:
        raise ValueError("CSV exceeds 20 MB")
    content = content.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(content, newline=""), dialect)
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("The CSV is empty")
    if not headers or not any(headers):
        raise ValueError("The CSV needs a header row")
    if len(set(headers)) != len(headers):
        raise ValueError("Duplicate column headings: rename them before uploading")
    rows = []
    for line_no, cells in enumerate(reader, 2):
        if not cells:
            continue
        if len(cells) != len(headers):
            raise ValueError(f"CSV line {line_no} has {len(cells)} cells; expected {len(headers)}")
        rows.append(cells)
    if not rows:
        raise ValueError("The CSV has no data rows")
    if len(rows) > 25000:
        raise ValueError("Please split inputs above 25,000 rows")
    lower = [x.strip().lower().replace("_", " ") for x in headers]
    name_col = next((i for i, h in enumerate(lower) if h in ("company", "name", "company name", "tool", "vendor", "organization", "title", "job title", "role")), 0)
    url_col = next((i for i, h in enumerate(lower) if h in ("job url", "posting url", "job posting url")),None)
    if url_col is None:
        url_col = next((i for i, h in enumerate(lower) if h in ("website", "url", "website url", "company url", "domain", "homepage")), None)
    mode="jobs" if any(h in ("job url","job id","posting url") for h in lower) else "companies"
    return {"headers": headers, "rows": rows, "row_count": len(rows), "name_column": name_col,
            "url_column": url_col, "detected_mode":mode,"job_columns":job_column_mapping(headers),
            "input_sha256": hashlib.sha256(content.encode()).hexdigest()}


def map_rows(parsed, name_column, url_column):
    width = len(parsed["headers"])
    if not 0 <= name_column < width or (url_column is not None and not 0 <= url_column < width):
        raise ValueError("Select valid name and website columns")
    return [{"row_id": f"R{i + 1:06d}", "position": i, "original": cells,
             "name": cells[name_column].strip(),
             "website": safe_url(cells[url_column]) if url_column is not None else ""}
            for i, cells in enumerate(parsed["rows"])]


def added_column_names(headers, desired):
    existing = set(headers)
    mapping = {}
    for name in desired:
        actual = name
        while actual in existing:
            actual = "zc_" + actual
        existing.add(actual)
        mapping[name] = actual
    return mapping


def export_csv(headers, rows):
    from .models import SIGNALS
    desired = ["row_id", "verdict", "latest_activity_date", "evidence_links", "confidence", "reason",
               "review_required", "audit_status", "identity_status", "canonical_url", "checked_at",
               "signals_checked", "signals_verified", "tinyset_dataset_id"]
    desired += [f"{s}_{field}" for s in SIGNALS for field in ("status", "date", "evidence_url", "evidence_quote", "verified")]
    desired += ["job_first_published", "job_updated_at", "current_job_title", "employer_name", "employer_website", "tinyset_scope", 'signup_observation_scope', 'signup_note']
    names = added_column_names(headers, desired)
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(headers + [names[k] for k in desired])
    for row in rows:
        result = row.get("result") or {}
        identity = result.get("identity") or {}
        values = dict(result)
        values.update(row_id=row["row_id"], audit_status=row["status"], identity_status=identity.get("status", "unknown"),
                      canonical_url=identity.get("canonical_url", ""), tinyset_dataset_id=row.get("dataset_id", ""))
        values["evidence_links"] = " | ".join(result.get("evidence_links") or [])
        values['signup_observation_scope']=result.get('signals',{}).get('signup',{}).get('observation_scope','')
        values['signup_note']=result.get('signals',{}).get('signup',{}).get('note','')
        for s in SIGNALS:
            signal = result.get("signals", {}).get(s, {})
            for field, key in (("status", "status"), ("date", "latest_date"), ("evidence_url", "url"), ("evidence_quote", "quote"), ("verified", "verified")):
                values[f"{s}_{field}"] = signal.get(key, "")
        writer.writerow(row["original"] + ["" if values.get(k) is None else values.get(k, "") for k in desired])
    return out.getvalue()

