import datetime as dt
import ipaddress
import json
import re
from urllib.parse import urlparse

SIGNALS = ("blog", "release", "jobs", "social", "signup")
STATUS = {"active", "inactive", "not_found", "blocked", "unknown", "not_applicable"}


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if re.search(r"[\s\x00-\x1f<>]", value):
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        return ""
    if host in ("localhost", "metadata.google.internal") or host.endswith((".local", ".localhost", ".internal")):
        return ""
    try:
        if not ipaddress.ip_address(host).is_global:
            return ""
    except ValueError:
        if "." not in host:
            return ""
    return value


def normalized(text):
    import html
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(text or "")))).strip().casefold()


def as_object(value):
    if isinstance(value, dict):
        return value.copy()
    try:
        result = json.loads(str(value or "{}"))
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def activity_date(value, today=None):
    today = today or dt.date.today()
    try:
        date = dt.date.fromisoformat(str(value)[:10])
        return date.isoformat() if dt.date(1990, 1, 1) <= date <= today else None
    except (ValueError, TypeError):
        return None


def signal_record(value, kind):
    result = as_object(value)
    status = str(result.get("status", "unknown")).lower()
    return {"kind": kind, "status": status if status in STATUS else "unknown",
            "latest_date": activity_date(result.get("latest_date")),
            "url": safe_url(result.get("url")), "quote": str(result.get("quote") or "")[:2000],
            "note": str(result.get("note") or "No verifiable observation returned.")[:3000],
            "checked_at": None, "verified": False, "date_verified": False,
            "method": "tinyset", "error": None}


def date_in_text(date, text):
    if not date:
        return False
    d = dt.date.fromisoformat(date)
    text = normalized("\n".join(line for line in str(text or "").splitlines()
                                 if not re.search(r"copyright|©|all rights reserved|effective date",line,re.I)))
    alternatives = [date, d.strftime("%B %d, %Y"), d.strftime("%b %d, %Y"),
                    f"{d.strftime('%B')} {d.day}, {d.year}", f"{d.strftime('%b')} {d.day}, {d.year}",
                    f"{d.day} {d.strftime('%B')} {d.year}", f"{d.day} {d.strftime('%b')} {d.year}"]
    return any(normalized(s) in text for s in alternatives)


def dated_activity(text):
    """Only explicit full dates in activity context; omit footer/copyright dates."""
    if re.search(r"(?:privacy policy|terms of (?:service|use)|effective date)",str(text or "")[:500],re.I) and not re.search(r"(?:release notes|changelog|product update)",str(text or "")[:500],re.I):
        return None
    candidates = []
    code_fence = None
    for line in str(text or "").splitlines():
        fence=re.match(r'^\s*(`{3,}|~{3,})',line)
        if fence:
            marker=fence.group(1)[0]
            code_fence=None if code_fence==marker else marker if code_fence is None else code_fence
            continue
        if code_fence or line.startswith(('    ','\t')):
            continue
        if re.search(r"copyright|©|all rights reserved|effective date|compatibility[_\\ ]date|set this to today|example (?:date|timestamp)|sample (?:date|timestamp)", line, re.I):
            continue
        for match in re.finditer(r"\b20\d{2}-\d{2}-\d{2}\b", line):
            value = activity_date(match.group())
            if value:
                candidates.append(value)
        for match in re.finditer(r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*20\d{2}\b", line, re.I):
            raw = match.group().replace(",", "")
            raw=re.sub(r"(\d)(?:st|nd|rd|th)",r"\1",raw)
            raw=re.sub(r"(\d{1,2})(20\d{2})$",r"\1 \2",raw)
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    value = activity_date(dt.datetime.strptime(raw, fmt).date().isoformat())
                    if value:
                        candidates.append(value)
                    break
                except ValueError:
                    pass
        for match in re.finditer(r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2}\b",line,re.I):
            for fmt in ("%d %B %Y","%d %b %Y"):
                try:
                    value=activity_date(dt.datetime.strptime(match.group(),fmt).date().isoformat())
                    if value:candidates.append(value)
                    break
                except ValueError:pass
    return max(candidates) if candidates else None

