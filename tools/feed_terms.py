"""Feed gate (GD6 phase 1): every feed needs a terms record before the data job may read it.
Records come from the lane's first-hand reading of each terms page (research/GD6/GD6-feed-terms-audit.md, 2026-11-16).
Rules: no record -> blocked. commercial == "no" -> blocked. A record older than MAX_AGE_DAYS -> blocked (read the terms again).
ads_ok says whether the feed may sit on a page that shows ads. Nothing shows ads yet; check it before any ad network application.
No feed text goes to a language model in this project: llm is a record of what the terms allow, for later.
"""
from datetime import date

MAX_AGE_DAYS = 180

FEED_TERMS = {
    "usgs-quakes": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit: U.S. Geological Survey", "ads_ok": True, "checked": "2026-11-16"},
    "nws-alerts": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA/NWS; do not present modified content as official; no implied endorsement", "ads_ok": True, "checked": "2026-11-16"},
    "nhc": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA/NHC; same NWS rule", "ads_ok": True, "checked": "2026-11-16"},
    "eonet": {"verdict": "OK with conditions", "commercial": "yes", "llm": "yes", "attribution": "Credit NASA EONET and the original source; never credit our text to NASA; no NASA insignia near ads", "ads_ok": True, "checked": "2026-11-16"},
    "usgs-volcano": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit: U.S. Geological Survey", "ads_ok": True, "checked": "2026-11-16"},
    "swpc-kp": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA SWPC", "ads_ok": True, "checked": "2026-11-16"},
    "spc-outlook": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA/NWS SPC", "ads_ok": True, "checked": "2026-11-16"},
    "hms-smoke": {"verdict": "OK (inferred)", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA/NESDIS HMS", "ads_ok": True, "checked": "2026-11-16"},
    "atd-faa": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit FAA via Air Travel Desk", "ads_ok": True, "checked": "2026-11-16"},
    "ms365": {"verdict": "UNCLEAR, medium risk", "commercial": "unclear", "llm": "unclear", "attribution": "Headline and link only; Microsoft terms say personal and non-commercial use", "ads_ok": False, "checked": "2026-11-16"},
    "openfda-food": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Data provided by the U.S. Food and Drug Administration", "ads_ok": True, "checked": "2026-11-16"},
    "cpsc": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit US Consumer Product Safety Commission", "ads_ok": True, "checked": "2026-11-16"},
    "cisa-kev": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit CISA; no CISA logo or DHS seal", "ads_ok": True, "checked": "2026-11-16"},
    "status-github": {"verdict": "UNCLEAR, low risk", "commercial": "unclear", "llm": "unclear", "attribution": "Headline and link only", "ads_ok": False, "checked": "2026-11-16"},
    "status-cloudflare": {"verdict": "UNCLEAR, low risk", "commercial": "unclear", "llm": "unclear", "attribution": "Headline and link only; use the Status API with an identifying User-Agent", "ads_ok": False, "checked": "2026-11-16"},
    "status-openai": {"verdict": "UNCLEAR, low risk", "commercial": "unclear", "llm": "unclear", "attribution": "Headline and link only", "ads_ok": False, "checked": "2026-11-16"},
    "status-atlassian": {"verdict": "UNCLEAR, low risk", "commercial": "unclear", "llm": "unclear", "attribution": "Headline and link only", "ads_ok": False, "checked": "2026-11-16"},
    "fedreg-presidential": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit Federal Register; 1 CFR 2.6 allows republishing", "ads_ok": True, "checked": "2026-11-16"},
    "fcdo": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Contains public sector information licensed under the Open Government Licence v3.0.", "ads_ok": True, "checked": "2026-11-16"},
    "eu-press": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit the European Commission (CC BY 4.0); note changes", "ads_ok": True, "checked": "2026-11-16"},
    "gdelt-doc": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Cite the GDELT Project and link https://www.gdeltproject.org/", "ads_ok": True, "checked": "2026-11-16"},
    "tsunami-ak": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA/NWS", "ads_ok": True, "checked": "2026-11-16"},
    "tsunami-hi": {"verdict": "OK", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA/NWS", "ads_ok": True, "checked": "2026-11-16"},
    "probes": {"verdict": "OK (our own)", "commercial": "yes", "llm": "n/a", "attribution": "Measured by the desk", "ads_ok": True, "checked": "2026-11-16"},
    "news-lane": {"verdict": "OK (GDELT terms)", "commercial": "yes", "llm": "yes", "attribution": "Cite the GDELT Project; show the outlet name and a link; headline only", "ads_ok": True, "checked": "2026-11-16"},
    "awc-sigmet": {"verdict": "OK (NOAA/NWS rules; the AWC page states no licence)", "commercial": "yes", "llm": "yes", "attribution": "Credit NOAA Aviation Weather Center; advisories, not flight cancellations", "ads_ok": True, "checked": "2026-11-16"},
    "gdacs": {"verdict": "UNCLEAR, low risk", "commercial": "unclear", "llm": "unclear", "attribution": "Credit GDACS; copyright notice points to the European Commission CC BY 4.0 legal notice", "ads_ok": False, "checked": "2026-11-16"},
}


def gate(src, today=None):
    """Return (ok, reason). ok is True when the feed may be read."""
    today = today or date.today()
    rec = FEED_TERMS.get(src["id"])
    if not rec:
        return False, "no terms record"
    if rec["commercial"] == "no":
        return False, "terms bar commercial use"
    try:
        age = (today - date.fromisoformat(rec["checked"])).days
    except ValueError:
        return False, "bad check date"
    if age > MAX_AGE_DAYS:
        return False, "terms record is %d days old" % age
    return True, ""


def ads_blockers(sources):
    """Feed ids that must be removed from, or kept off, pages that show ads."""
    return sorted(s["id"] for s in sources if not FEED_TERMS.get(s["id"], {}).get("ads_ok"))


# Tip feeds (GD8 part 7). INTERNAL READ ONLY: headline, link and time are read for tips and never published or shown on the site.
# Terms were not all read first-hand. Read each outlet's terms before any use that goes beyond internal reading.
TIP_FEEDS = {
    "aljazeera": {"terms_read": False, "note": "Public RSS. Internal tip reading only. Terms not read."},
    "cnn": {"terms_read": False, "note": "Public RSS. Internal tip reading only. The RSS page returned HTTP 451 in our browser, so its terms were not read."},
    "bbc": {"terms_read": False, "note": "Public RSS. Internal tip reading only. Terms page could not be fetched."},
    "npr": {"terms_read": True, "note": "NPR terms allow content feeds on personal or 501(c)(3) non-news sites. We do not display them. Internal tip reading only."},
    "guardian": {"terms_read": False, "note": "Public RSS. Internal tip reading only. Terms not read."},
    "cbs": {"terms_read": True, "note": "RSS page states no reuse terms. Internal tip reading only."},
    "nbc": {"terms_read": False, "note": "Public RSS. Internal tip reading only. Terms not read."},
    "ap": {"terms_read": False, "note": "No public feed found (HTTP 403). Not used."},
}
