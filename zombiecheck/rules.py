import datetime as dt
from .models import SIGNALS, activity_date, utcnow

RULE_VERSION = "1.3"
DEAD_IDENTITIES = {"closed", "acquired_discontinued", "parked"}


def classify(signals, identity, homepage=None, closure=None, today=None, stale_days=365):
    today = today or dt.date.today()
    verified = [signals[s] for s in SIGNALS if signals.get(s, {}).get("verified")]
    checked = [signals[s] for s in SIGNALS if signals.get(s, {}).get("checked_at")]
    active = [s for s in verified if s["status"] == "active"]
    dates = [s["latest_date"] for s in verified if s.get("date_verified") and activity_date(s.get("latest_date"), today)]
    latest = max(dates) if dates else None
    recent = [s for s in active if s.get("date_verified") and s.get("latest_date") and
              (today - dt.date.fromisoformat(s["latest_date"])).days <= 90]
    operating = any(s["kind"] in ("signup", "jobs") for s in active)
    identity_ok = identity.get("verified") and identity.get("status") not in DEAD_IDENTITIES | {"ambiguous", "unknown"}
    conflicts = bool(identity.get("status") in DEAD_IDENTITIES and (recent or operating))
    confirmed_closed = bool(closure and closure.get("verified") and closure.get("status") == "confirmed")
    conflicts = conflicts or bool(confirmed_closed and (recent or operating))
    parked = bool(identity.get("verified") and identity.get("status") == "parked")
    verdict, confidence, reason, review = "", "insufficient", "Evidence needs review before assigning a verdict.", True
    if (confirmed_closed or parked or (identity.get("verified") and identity.get("status") in ("closed", "acquired_discontinued"))) and not conflicts:
        verdict, confidence, review = "zombie", "high", False
        reason = "Corroborated inactive accelerator profile and missing original homepage." if closure and closure.get("corroboration") else "Explicit closure/discontinuation evidence." if not parked else "The original domain is parked and no operating successor was established."
    elif identity_ok and (recent or (operating and homepage and homepage.get("verified"))):
        verdict, confidence, review = "alive", "high" if recent and operating else "medium", False
        reason = "Recent dated activity on a verified source." if recent else "The company page is live and its onboarding or open hiring is verified."
    elif identity_ok and homepage and homepage.get("verified") and latest and (today - dt.date.fromisoformat(latest)).days > 90:
        verdict, confidence, review = "slowing down", "medium", False
        reason = "The website is operating, but the latest verified activity is more than 90 days old."
    elif identity_ok and len(set(s.get("url") for s in active)) >= 2:
        verdict, confidence, review = "alive", "medium", False
        reason = "Two distinct verified operational signals; a recent activity date was not established."
    elif identity_ok and homepage and homepage.get("verified") and len(verified) >= 4:
        verdict, confidence, review = "slowing down", "low", True
        reason = "Website reachable; four checks found limited activity. Manual review is needed to distinguish a quiet company."
    if conflicts:
        verdict, confidence, review = "", "insufficient", True
        reason = "Closure/parking evidence conflicts with operating signals; resolve the company identity."
    if len(checked) < 4:
        verdict, confidence, review = "", "insufficient", True
        reason = "Fewer than four live signal checks have finished."
    urls = list(dict.fromkeys([s.get("url") for s in checked if s.get("url")] +
                             [x.get("url") for x in (identity, homepage or {}, closure or {}) if x.get("url")]))
    return {"verdict": verdict, "confidence": confidence, "reason": reason, "review_required": review,
            "latest_activity_date": latest, "evidence_links": urls, "signals_checked": len(checked),
            "signals_verified": len(verified), "checked_at": utcnow(), "rule_version": RULE_VERSION,
            "identity": identity, "homepage": homepage or {}, "closure": closure or {}, "signals": signals}

