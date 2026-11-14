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
    if t == "earthquake":
        return max(0, min(30, (s - 4.5) * 10))
    if t == "storm":
        return max(0, min(30, s / 5))
    if t == "wildfire":
        return min(30, math.log10(s + 1) * 6)
    if t == "weather":
        return min(30, 6 * math.log2(s + 1))
    if t == "tsunami":
        return 30
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
        if d.get("tsunami_flag"):
            s += " The USGS tsunami flag is set. Check tsunami.gov for official messages."
        return s
    if t == "weather":
        return "The National Weather Service has %d active %s alert%s in %s. Location shown is the state centre." % (
            d["alerts"], e["title"].lower(), "" if d["alerts"] == 1 else "s", place.split(",")[0])
    if t == "storm":
        if d.get("wind_mph"):
            return "The National Hurricane Center lists %s with sustained winds near %d mph." % (e["title"], d["wind_mph"])
        return "GDACS lists %s." % e["title"]
    if t == "wildfire":
        if d.get("magnitude"):
            return "A wildfire is open in the NASA EONET list. Reported size: %s %s." % (_num(d["magnitude"]), d.get("unit") or "")
        return "A wildfire is open in the NASA EONET list. No size is reported."
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
           "Center", "Aurora", "Follow", "Tsunami", "Warning", "Watch", "Advisory", "Pacific", "Alaska", "Hawaii", "Bulletin", "Kp", "NOAA", "Observatory", "Program", "NASA", "EONET", "GDACS", "USGS", "Reported", "Wildfire", "Earthquake", "Listed", "Alert", "Level"}


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
