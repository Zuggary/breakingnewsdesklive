"""Shared helpers: time, distance, regions, score, templated summaries, and the summary guard."""
import math
import re
from datetime import datetime, timezone

STATE_CENTROIDS = {
    "AL": (32.8, -86.8, "Alabama"), "AK": (64.2, -152.3, "Alaska"), "AZ": (34.3, -111.7, "Arizona"),
    "AR": (34.9, -92.4, "Arkansas"), "CA": (37.2, -119.5, "California"), "CO": (39.0, -105.5, "Colorado"),
    "CT": (41.6, -72.7, "Connecticut"), "DE": (39.0, -75.5, "Delaware"), "DC": (38.9, -77.0, "District of Columbia"),
    "FL": (28.6, -82.4, "Florida"), "GA": (32.7, -83.4, "Georgia"), "HI": (20.8, -156.3, "Hawaii"),
    "ID": (44.4, -114.6, "Idaho"), "IL": (40.0, -89.2, "Illinois"), "IN": (39.9, -86.3, "Indiana"),
    "IA": (42.1, -93.5, "Iowa"), "KS": (38.5, -98.4, "Kansas"), "KY": (37.5, -85.3, "Kentucky"),
    "LA": (31.1, -92.0, "Louisiana"), "ME": (45.4, -69.2, "Maine"), "MD": (39.0, -76.8, "Maryland"),
    "MA": (42.2, -71.5, "Massachusetts"), "MI": (44.3, -85.4, "Michigan"), "MN": (46.3, -94.3, "Minnesota"),
    "MS": (32.7, -89.7, "Mississippi"), "MO": (38.4, -92.5, "Missouri"), "MT": (47.0, -109.6, "Montana"),
    "NE": (41.5, -99.8, "Nebraska"), "NV": (39.3, -116.6, "Nevada"), "NH": (43.7, -71.6, "New Hampshire"),
    "NJ": (40.1, -74.7, "New Jersey"), "NM": (34.4, -106.1, "New Mexico"), "NY": (42.9, -75.5, "New York"),
    "NC": (35.6, -79.4, "North Carolina"), "ND": (47.5, -100.5, "North Dakota"), "OH": (40.3, -82.8, "Ohio"),
    "OK": (35.6, -97.5, "Oklahoma"), "OR": (43.9, -120.6, "Oregon"), "PA": (40.9, -77.8, "Pennsylvania"),
    "RI": (41.7, -71.5, "Rhode Island"), "SC": (33.9, -80.9, "South Carolina"), "SD": (44.4, -100.2, "South Dakota"),
    "TN": (35.8, -86.3, "Tennessee"), "TX": (31.5, -99.3, "Texas"), "UT": (39.3, -111.7, "Utah"),
    "VT": (44.1, -72.7, "Vermont"), "VA": (37.5, -78.8, "Virginia"), "WA": (47.4, -120.5, "Washington"),
    "WV": (38.6, -80.6, "West Virginia"), "WI": (44.6, -89.9, "Wisconsin"), "WY": (43.0, -107.5, "Wyoming"),
    "PR": (18.2, -66.5, "Puerto Rico"), "GU": (13.4, 144.8, "Guam"), "VI": (18.3, -64.8, "US Virgin Islands"),
    "AS": (-14.3, -170.7, "American Samoa"), "MP": (15.2, 145.7, "Northern Mariana Islands"),
}

REGIONS = ["Americas", "Europe", "Africa", "Middle East", "Asia", "Oceania", "Ocean"]


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(s):
    s = s.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def haversine_km(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def region_of(lat, lon, place=""):
    if lat is None or lon is None:
        return "Ocean"
    if -170 <= lon <= -30 and -60 <= lat <= 80 and (lon <= -52 or (lat < -5 and lon <= -34) or (lat > 60 and lon <= -20)):
        return "Americas"
    if 34 <= lon <= 60 and 12 <= lat <= 42 and lon > 34 and not (lon < 40 and lat < 22):
        return "Middle East"
    if -25 <= lon <= 45 and 35 <= lat <= 72:
        return "Europe"
    if -20 <= lon <= 52 and -36 <= lat < 35:
        return "Africa"
    if 60 <= lon <= 180 and lat >= -10 and not (110 <= lon and lat < 0):
        return "Asia"
    if 95 <= lon <= 180 and lat < 10 or lon <= -150 and lat < 25 or lon >= 165:
        return "Oceania"
    if 45 <= lon <= 60 and lat >= 12:
        return "Middle East"
    return "Ocean"


SEV_POINTS = {"extreme": 50, "severe": 38, "moderate": 24, "minor": 10}


def size_points(e):
    t, s = e["type"], e.get("size") or 0
    try:
        s = float(s)
    except (TypeError, ValueError):
        s = 0.0
    if t == "earthquake":
        return max(0, min(30, (s - 4.5) * 10))
    if t == "storm":
        return max(0, min(30, s / 5))
    if t == "wildfire":
        return min(30, math.log10(s + 1) * 6)
    if t == "weather":
        return min(30, 6 * math.log2(s + 1)) if s else 12
    if t == "tsunami":
        return 30
    if t == "transport":
        return min(30, 8 + s / 3)
    if t == "statement":
        return 6
    if t == "headline":
        return min(12, 2 * s)
    if t == "recall":
        return 10
    if t == "notice":
        return 8
    if t == "cyber":
        return min(20, 8 + s)
    if t == "outage":
        d = e.get("detail") or {}
        if not d.get("open"):
            return 4
        return 10 if d.get("impact") in ("minor", "") and d.get("provider") else 20
    if t == "smoke":
        return min(10, 3 * math.log2(s + 1))
    return 12


def score_event(e, now):
    age_h = max(0, (now - parse_time(e["time"])).total_seconds() / 3600)
    fresh = 20 * math.exp(-age_h / 24)
    sev = SEV_POINTS.get(e["severity"], 10)
    if e["type"] == "weather" and e["severity"] != "extreme":
        sev = 16  # routine US warnings (freeze, wind) rank below large global events
    return round(min(100, sev + size_points(e) + fresh), 1)


def ago(e, now):
    h = (now - parse_time(e["time"])).total_seconds() / 3600
    return "%d minutes" % max(1, round(h * 60)) if h < 1 else "%d hours" % round(h) if h < 48 else "%d days" % round(h / 24)


def summarize(e):
    """Plain-word summary built from a template. Uses only values that are in the event."""
    d, t, place = e.get("detail") or {}, e["type"], e["place"]
    if t == "earthquake":
        s = "A magnitude %.1f earthquake was recorded. Location: %s. Depth was about %d km." % (d["magnitude"], place, d["depth_km"])
        if d.get("pager") in ("yellow", "orange", "red"):
            s += " USGS PAGER impact level: %s." % d["pager"]
        if d.get("tsunami_flag"):
            s += " The USGS tsunami flag is set. Check tsunami.gov for official messages."
        return s
    if t == "weather" and d.get("risk"):
        return "The Storm Prediction Center rates today's severe thunderstorm risk as %s in part of the United States. This outlook is valid until %s. The map point is the centre of the risk area." % (d["risk"], d["valid_until"])
    if t == "weather":
        return "The National Weather Service has %d active %s alert%s in %s. Location shown is the state centre." % (
            d["alerts"], e["title"].lower(), "" if d["alerts"] == 1 else "s", place.split(",")[0])
    if t == "aviation":
        return "An aviation weather advisory (%s SIGMET) is in force for the %s flight information region. It is valid until %s. Cloud top near %d ft. This is an advisory for pilots, not a flight cancellation." % (d["hazard"], d["fir"], d["valid_to"], d["top_ft"] or 0)
    if t == "storm":
        if d.get("wind_mph"):
            return "The National Hurricane Center lists %s with sustained winds near %d mph." % (e["title"], d["wind_mph"])
        return "GDACS lists %s." % e["title"]
    if t == "wildfire":
        if d.get("magnitude"):
            return "A wildfire is open in the NASA EONET list. Reported size: %s %s." % (_num(d["magnitude"]), d.get("unit") or "")
        return "A wildfire is open in the NASA EONET list. No size is reported."
    if t == "transport":
        s = "FAA status for %s (%s): %s." % (e["place"], d["airport_code"], d["kind"].lower())
        if d.get("reason") and d["reason"].lower().rstrip(".") != d["kind"].lower():
            s += " Reason given: %s." % d["reason"].rstrip(".")
        if d.get("avg_delay_text"):
            s += " Average delay reported: %s." % d["avg_delay_text"].rstrip(".")
        elif d.get("avg_delay_min"):
            s += " Average delay reported: %d minutes." % d["avg_delay_min"]
        if d.get("until"):
            s += " Expected until: %s" % d["until"]
        return s
    if t == "statement":
        return "%s published this on %s: %s. The desk shows the title and links to the source. It does not summarise or check the text." % (d["party"], d["published"], d["headline"])
    if t == "headline":
        return "%d sites published headlines about the same event. First seen %s. Sites shown: %s. These are the sites' own headlines. Sites that share an owner or a wire service can repeat one story. The desk has not checked them." % (d["outlets"], d["first_seen"], d["outlet_names"])
    if t == "notice":
        return "The Federal Register lists this presidential document, published %s: %s." % (d["published"], d["title"])
    if t == "recall":
        if d.get("class"):
            return "FDA lists a %s recall by %s. Product: %s. Reason given: %s." % (d["class"], d["firm"], d["product"], d["reason"].rstrip("."))
        return "The US Consumer Product Safety Commission lists this recall: %s." % d["headline"]
    if t == "cyber":
        return "CISA added %d vulnerabilities to its known exploited catalog on %s. Vendors named: %s. Read the catalog for details." % (d["count"], d["date_added"], d["vendors"])
    if t == "outage" and d.get("provider"):
        return "%s's public status page lists an open incident: %s. Status: %s. Impact level: %s." % (d["provider"], d["incident"], d["status"], d["impact"] or "not given")
    if t == "outage":
        if d.get("open"):
            return "Microsoft's public status page shows an open incident since %s. Current status: %s." % (d["since"], d["status"])
        return "Microsoft's public status page shows the last incident ended. It ran about %s hours from %s." % (_num(d["hours"]), d["started"])
    if t == "smoke":
        return "NOAA satellite analysis shows %d %s-density smoke plumes. The map point marks the largest plume. Smoke can affect air quality far from the fire." % (d["plumes"], d["density"].lower())
    if t == "tsunami":
        return "%s issued: %s. Follow the instructions of local officials and read the full bulletin at tsunami.gov." % (d["centre"], d["bulletin"])
    if t == "space":
        return "NOAA reports a planetary Kp index of %s, a G%d geomagnetic storm level. Aurora may be visible farther south than usual." % (_num(d["kp"]), d["g_scale"])
    if t == "volcano" and d.get("volcano"):
        return "%s lists %s at alert level %s, colour code %s." % (d["observatory"], d["volcano"], d["alert_level"], d["color_code"])
    if t in ("flood", "volcano", "drought"):
        lvl = d.get("alert_level")
        txt = "GDACS lists a %s event: %s." % (t, e["title"])
        if lvl:
            txt += " GDACS alert level: %s." % lvl
        return txt
    return "Listed by %s: %s." % (e["source"], e["title"])


def _num(x):
    return str(int(x)) if float(x) == int(x) else str(x)


# ---------- guard ----------
_NUM = re.compile(r"\d+(?:\.\d+)?")
_WORD = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_COMMON = {"The", "This", "That", "National", "Weather", "Service", "Check", "Depth", "Location", "State", "Hurricane",
           "Center", "Outlets", "Sites", "First", "These", "Headline", "Foreign", "Office", "Commission", "European", "Federal", "Register", "FDA", "CISA", "Consumer", "Product", "Safety", "Commission", "Vendors", "Software", "Read", "Class", "Impact", "Status", "Airport", "Microsoft", "Microsoft's", "Reason", "Expected", "Average", "Current", "FAA", "Delays", "Ground", "Stop", "Closed", "PAGER", "Smoke", "NOAA", "Storm", "Prediction", "Aurora", "Follow", "Tsunami", "Warning", "Watch", "Advisory", "Pacific", "Alaska", "Hawaii", "Bulletin", "Kp", "NOAA", "Observatory", "Program", "NASA", "EONET", "GDACS", "USGS", "Reported", "Wildfire", "Earthquake", "Listed", "Alert", "Level"}


CLAIM_RE = re.compile(r"\b(kill(?:ed|s|ing)?|dead|deaths?|died|casualt\w+|victims?|fatalit\w+|suspects?|arrest(?:ed|s)?|blam(?:e|es|ed)|perpetrators?|gunman|terroris[mt]s?|massacre|hostages?)\b", re.I)
SAFE_SUMMARY = "The source lists this item. This site does not repeat unverified claims. Check the source page."


def claims_ok(text):
    """False when generated text holds blame, suspect or casualty words. Only the source may say these."""
    return not CLAIM_RE.search(text or "")


def status_label(e, now):
    """UNVERIFIED for claims by an outlet or a party. DEVELOPING for any other event under 90 minutes old. Otherwise empty."""
    if e["type"] in ("headline", "statement"):
        return "UNVERIFIED"
    age_min = (now - parse_time(e["time"])).total_seconds() / 60
    return "DEVELOPING" if age_min < 90 else ""


def guard_ok(summary, event):
    """True only if every number and every capitalised word in `summary` appears in the event data."""
    blob = " ".join(str(v) for v in _flat(event)).lower()
    for n in _NUM.findall(summary):
        if n.lower() not in blob and n.rstrip("0").rstrip(".").lower() not in blob:
            return False
    for w in _WORD.findall(summary):
        if w not in _COMMON and w.lower() not in blob:
            return False
    return True


def _flat(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _flat(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _flat(v)
    elif x is not None:
        yield x
