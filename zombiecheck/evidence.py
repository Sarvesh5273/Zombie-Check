"""High precision observations. Research text is untrusted until checked."""
import re
from urllib.parse import urlparse, urljoin
from .models import SIGNALS, normalized, safe_url, utcnow, dated_activity, date_in_text, signal_record, as_object, activity_date

PARKING = r"\b(?:this domain (?:is for sale|may be for sale)|buy this domain|domain (?:name )?for sale|domain parking|sedo domain parking|hugedomains)\b"
CLOSURE = r"\b(?:we (?:have |are |will be )?(?:shut(?:ting)? down|clos(?:ed|ing))|has (?:shut down|closed its doors)|ceased operations|no longer (?:operational|available)|discontinu(?:ing|ed) (?:our|the) (?:product|service)|end of (?:life|service)|shutdown|sunset(?:ting|ted))\b"
REBRAND = r"\b(?:formerly known as|rebrand(?:ed|ing)|changed (?:our|its) name|is now called)\b"
ACQUIRED = r"\b(?:acquired by|acquires?|acquisition|joined (?:forces|the .* team))\b"


def short_quote(text,pattern=None):
    lines=[line.strip() for line in str(text or "").splitlines() if line.strip()]
    if pattern:
        for line in lines:
            if re.search(pattern,line,re.I):
                return line[:500]
    return " ".join(lines[:2])[:300]


def host(url):
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def related_host(a,b):
    a,b=host(a),host(b)
    return bool(a and b and (a==b or a.endswith("."+b) or b.endswith("."+a)))


def closure_quote(name,text,official=False):
    """Require organization-level closure language in the same local passage."""
    escaped=re.escape(name)
    # A name occurring inside blog.example.com or an article URL is not the
    # subject of an organization-level closure announcement.
    subject=rf'(?<![\w./@-]){escaped}(?![\w./@-])'
    patterns=[rf"{subject}.{{0,100}}\b(?:shut down|shutting down|ceased operations|closed its doors|will close|will shut down)",
              rf"{subject}.{{0,40}}\b(?:is no longer running|is no longer operating|is no longer available)",
              rf"\b(?:closure|shutdown|shutting down|shut down)\b.{{0,80}}{subject}"]
    if official:
        patterns += [r"\bwe (?:are |will be |have )?shut(?:ting)? down(?:\s+(?:our company|the company|our business|operations))?[.!]",
                     r"\bwe (?:have )?shut down our (?:company|business)(?: and ceased operations)?[.!]",
                     r"\bwe (?:have )?ceased operations\b"]
    for line in str(text or "").splitlines():
        if len(line)>2500 or re.search(r"\b(?:feature|legacy|old api|deprecated|deprecated endpoint|single product|office|studio|warehouse|location|division|blog|wordpress|newsletter|forum|community server)\b",line,re.I):
            continue
        if any(re.search(p,line,re.I) for p in patterns):
            return line.strip()[:700]
    return ""


def page_text(page):
    text=page.get("text","")
    return text if isinstance(text,str) else str(text)


def identity_from_page(row,page):
    original,final=row["website"],page.get("final_url",row["website"])
    text=page_text(page)
    original_host,final_host=host(original),host(final)
    status="same" if original_host==final_host else "ambiguous"
    verified=bool(text.strip()) and status=="same"
    note="Original website resolves to a live page."
    if status=="ambiguous":
        note="Redirect to a different domain requires explicit successor/identity evidence."
    named_parking=re.search(re.escape(original_host)+r"\s+(?:is|may be) for sale",normalized((page.get("title") or "")+" "+text),re.I)
    if re.search(PARKING,text,re.I) or named_parking:
        status,verified,note="parked",True,"Live page explicitly offers the original domain for sale/parking."
    # A generic closure word in somebody else's article does not identify this company.
    shutdown=closure_quote(row["name"],text,official=True)
    if shutdown and status=="same":
        status,note="closed","Original homepage explicitly announces closure."
    return {"status":status,"canonical_url":safe_url(final),"url":original,"current_name":row["name"],
            "quote":shutdown if status=="closed" else short_quote(text,PARKING if status=="parked" else None),
            "note":note,"verified":verified,"checked_at":page.get("checked_at",utcnow())}


def discover_signal_urls(page,base):
    links=[safe_url(u) for u in page.get("links",[]) if safe_url(u)]
    result={}
    patterns={"blog":r"/(?:blog|newsroom|news|articles)(?:/|$)",
              "release":r"/(?:changelog|changes|releases|whats-new|updates)(?:/|$)",
              "jobs":r"/(?:careers?|jobs|join-us)(?:/|$)|(?:boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com)/",
              "social":r"(?:linkedin\.com/company/|x\.com/|twitter\.com/|github\.com/)",
              "signup":r"/(?:sign[-_]?up|register|registration|get-started|start|onboarding)(?:/|\?|$)"}
    for kind,pattern in patterns.items():
        candidates=[u for u in links if re.search(pattern,u,re.I) and
                    (related_host(u,base) or kind in ("social","jobs") or (kind=="signup" and re.search(r"(?:auth0\.com|clerk\.accounts\.dev)",host(u))))]
        result[kind]=next((u for u in candidates if host(u)==host(base)),None) or (candidates[0] if candidates else "")
    fallback={"blog":"/blog","release":"/changelog","jobs":"/careers","signup":"/signup"}
    for kind,suffix in fallback.items():
        if not result.get(kind):
            result[kind]=urljoin(base,suffix)
    # Social cannot be guessed from the name; homepage checks record that no official link was found.
    if not result.get("social"):
        result["social"]=base
    return result


def observe_page(kind,url,page=None,error=None,linked=False,company_url=None):
    record=signal_record({},kind)
    record.update(url=url,checked_at=utcnow(),method="tinyfetch")
    if error:
        code=error.get("error",error.get("code","unknown"))
        record.update(error=code,note="Live fetch returned "+str(code),
                      status="not_found" if code=="page_not_found" else "blocked" if code in ("bot_blocked","login_required") else "unknown")
        # 404 is evidence that this URL is missing, not that the company is dead.
        record["verified"]=code=="page_not_found"
        return record
    if not page:
        record["error"]="no_response"
        return record
    text=page_text(page)
    lower=normalized(text)
    actual=page.get("final_url",url)
    record["url"]=actual
    if not text.strip():
        record["error"]="empty_content"
        return record
    trusted=related_host(actual,company_url or url) or (linked and kind in ("jobs","social","signup"))
    if not company_url and kind in ("blog","release") and not linked:
        trusted=False
    if not trusted:
        record.update(error="unverified_source_identity",quote=short_quote(text),note="Ownership of this source could not be verified; its activity cannot establish the original company's status.")
        return record
    if re.search(PARKING,text,re.I):
        record.update(status="inactive",quote=short_quote(text,PARKING),verified=True,note="Requested signal page is a parked domain.")
        return record
    if kind in ("blog","release"):
        legal=re.search(r"(?:privacy policy|terms of (?:service|use)|effective date)",text[:500],re.I) and not re.search(r"(?:release notes|changelog|product update)",text[:500],re.I)
        metadata_date=activity_date(page.get('published_date'))
        date=None if legal else metadata_date or dated_activity(text)
        record.update(latest_date=date,date_verified=bool(date),status="active" if date else "unknown",
                      quote=short_quote(text,re.escape(date)) if date else short_quote(text),
                      verified=bool(date),note="Explicit dated activity found on this live page." if date else "No full activity date could be verified on the page.")
        if date and metadata_date:
            record["note"]="Publication date extracted from metadata on this live source page."
            record["date_source"]="page_metadata"
            import json
            record['quote']=json.dumps({'title':page.get('title'),'published_date':page.get('published_date')},ensure_ascii=False)
            record['quote_format']='extracted_metadata'
    elif kind=="jobs":
        pattern=r"\b(?:[1-9]\d*\s*open (?:positions|roles|jobs)|apply (?:for|now)|view (?:open )?(?:positions|roles|jobs)|current openings|open roles)\b"
        none=r"\b(?:no (?:current |open |available )?(?:positions|roles|jobs|openings)|not currently hiring)\b"
        positive=re.search(r"\b(?:[1-9]\d*\s*open (?:positions|roles|jobs)|apply (?:for|now))\b",lower) or (re.search(r"\b(?:engineer|designer|manager|sales)\b",lower) and re.search(r"\b(?:remote|full.time|hybrid|on.site)\b",lower))
        if positive:
            record.update(status="active",verified=True,quote=short_quote(text,pattern),note="Live careers/ATS page lists hiring evidence; open jobs do not prove company growth.")
        elif re.search(none,lower) and not re.search(r"for (?:this|the) (?:specific )?(?:location|team|filter)",lower):
            record.update(status="inactive",verified=True,quote=short_quote(text,none),note="Official careers page explicitly reports no open roles.")
        else:
            record.update(quote=short_quote(text),note="Careers page was checked; open roles could not be confirmed.")
    elif kind=="signup":
        pattern=r"\b(?:create (?:an? |your )?(?:account|workspace)|sign up|register|start (?:your |a )?(?:free )?trial|work email)\b"
        form_language=re.search(r"\b(?:create (?:an? |your )?(?:account|workspace)|password|continue with (?:google|github)|sign up with (?:google|github)|start (?:your |a )?(?:free )?trial)\b",lower)
        if re.search(pattern,lower) and form_language and not (re.search(r"\b(?:newsletter|subscribe for updates|join our mailing list)\b",lower) and not re.search(r"\b(?:create .*account|password|workspace|trial)\b",lower)):
            record.update(status="active",verified=True,quote=short_quote(text,pattern),note="Registration entry/form text reachable. Account creation and backend submission were not tested.")
        else:
            record.update(quote=short_quote(text),note="Onboarding URL checked; a usable registration form was not established.")
    elif kind=="social":
        if linked and re.search(r"github\.com|linkedin\.com|x\.com|twitter\.com",url):
            date=dated_activity(text)
            record.update(status="active" if date else "unknown",latest_date=date,date_verified=bool(date),verified=bool(date),
                          quote=short_quote(text),note="Official profile linked by company homepage; dated activity verified." if date else "Official profile visited; latest full activity date unavailable.")
        elif related_host(url,company_url or url) and not re.search(r"github\.com|linkedin\.com|x\.com|twitter\.com",url):
            record.update(status="not_found",verified=True,quote=short_quote(text),note="Live homepage checked for official social/repository links; none were found. This is not proof of inactivity.")
        else:
            record.update(status="unknown",quote=short_quote(text),note="Profile was checked, but ownership/activity could not be verified.")
    return record


def verify_claim(value,page,kind):
    record=signal_record(value,kind)
    text=page_text(page)
    quote=record["quote"]
    record.update(checked_at=utcnow(),method="tinyset+tinyfetch")
    if quote and len(normalized(quote))>=8 and normalized(quote) in normalized(text):
        record["verified"]=True
        record["date_verified"]=date_in_text(record["latest_date"],text)
    else:
        record["error"]="quote_not_on_page"
    return record


def apply_identity_evidence(row,identity,page):
    text=page_text(page)
    mentions=normalized(row["name"]) in normalized(text)
    official=host(page.get("final_url",page.get("url")))==host(row["website"])
    source_identity=official or host(row["website"]) in normalized(text) or any(related_host(u,row["website"]) for u in page.get("links",[]))
    if not source_identity:
        return None
    if mentions and re.search(REBRAND,text,re.I) and official:
        identity.update(status="rebranded",verified=bool(identity.get("verified")),url=page["url"],quote=short_quote(text,REBRAND),note="Original official page announces a rebrand. Successor URL needs verification if the website moved.")
    acquisition_pattern=rf"\b{re.escape(row['name'])}\b.{{0,80}}\b(?:acquired by|was acquired|has been acquired)|\b(?:acquired|acquires)\s+{re.escape(row['name'])}\b"
    acquisition_line=next((line for line in text.splitlines() if len(line)<1500 and re.search(acquisition_pattern,line,re.I)),None)
    if mentions and acquisition_line:
        continuity=identity.get("verified") and identity.get("status") in ("same","acquired_operating","rebranded")
        identity.update(status="acquired_operating" if continuity else "ambiguous",
                        verified=bool(continuity),url=page["url"],quote=acquisition_line.strip()[:700],note="Acquisition verified. Original product continuity is evaluated separately.")
    quote=closure_quote(row["name"],text,official=official)
    if quote:
        return {"status":"confirmed","url":page["url"],"quote":quote,"note":"Explicit organization-level closure language names the supplied company/product.","verified":True}
    return None


def inactive_directory_evidence(row,identity,page,homepage):
    """Corroborate abandonment with an actual live accelerator profile, never input labels."""
    text=page_text(page)
    official=host(page.get("final_url",page.get("url")))=="ycombinator.com"
    error=homepage.get("error") or {}
    terminal=error.get("error")=="page_not_found" and error.get("status") in (404,410)
    final=page.get("final_url",page.get("url",""))
    reference=row.get("reference_url")
    slug=re.sub(r"[^a-z0-9]+","-",row["name"].casefold()).strip("-")
    identity_match=(final.rstrip("/")==reference.rstrip("/")) if reference else (urlparse(final).path.rstrip("/")=="/companies/"+slug)
    title=normalized(page.get("title") or "")
    title_match=bool(re.match(re.escape(normalized(row["name"]))+r"(?:\s*[|:–—-]|$)",title)) or any(normalized(line.lstrip("# "))==normalized(row["name"]) for line in text.splitlines()[:10])
    inactive=re.search(r"(?im)^\s*(?:\*+)?status(?:\*+)?\s*:?\s*(?:\n\s*)?inactive\s*$",text)
    if official and identity_match and title_match and terminal and inactive and not homepage.get("verified"):
        quote=inactive.group().strip()
        identity.update(status="closed",verified=True,url=page["url"],quote=quote,note="Live YC profile lists the original company as inactive, corroborated by an unavailable original homepage.")
        return {"status":"confirmed","verified":True,"url":page["url"],"quote":quote,"note":identity["note"],"corroboration":homepage.get("error")}
    return None

