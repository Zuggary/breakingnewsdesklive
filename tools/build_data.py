#!/usr/bin/env python3
"""Build data/events.json and data/sources.json from public and government feeds.

Usage: python tools/build_data.py --out data [--fixtures DIR]
Standard library only. Each source fails alone: one bad feed never stops the build.
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.lib import (REGIONS, region_of, score_event, summarize, STATE_CENTROIDS,  # noqa: E402
                       iso_utc, parse_time, haversine_km)

FIXTURE_MODE = False
FIXTURE_DIR = None
OUT_DIR = None
UA = "breakingnewsdesklive/1.0 (+https://breakingnewsdesklive.com; independent alert aggregator)"
MAX_AGE_H = 72
MAX_AGE_LONG_H = 168  # open fires, floods and volcanoes stay listed for 7 days

SOURCES = [
    {"id": "usgs-quakes", "update": "about every minute", "name": "USGS Earthquake Hazards Program",
     "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson",
     "page": "https://earthquake.usgs.gov/earthquakes/map/",
     "licence": "US Government work, public domain; credit USGS",
     "terms": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"},
    {"id": "nws-alerts", "update": "about every minute", "name": "US National Weather Service",
     "url": "https://api.weather.gov/alerts/active?status=actual&severity=Extreme,Severe",
     "page": "https://www.weather.gov/alerts",
     "licence": "US Government work, public domain; credit NOAA/NWS",
     "terms": "https://www.weather.gov/disclaimer"},
    {"id": "nhc", "update": "every few hours while storms are active", "name": "NOAA National Hurricane Center",
     "url": "https://www.nhc.noaa.gov/CurrentStorms.json",
     "page": "https://www.nhc.noaa.gov/",
     "licence": "US Government work, public domain; credit NOAA/NHC",
     "terms": "https://www.weather.gov/disclaimer"},
    {"id": "eonet", "update": "several times a day", "name": "NASA EONET",
     "url": "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=200",
     "page": "https://eonet.gsfc.nasa.gov/",
     "licence": "NASA open data; credit NASA EONET and the original source",
     "terms": "https://www.nasa.gov/nasa-brand-center/images-and-media/"},
    {"id": "usgs-volcano", "update": "when an observatory changes a level", "name": "USGS Volcano Hazards Program",
     "url": "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes",
     "page": "https://volcanoes.usgs.gov/",
     "licence": "US Government work, public domain; credit USGS",
     "terms": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"},
    {"id": "swpc-kp", "update": "every 3 hours", "name": "NOAA Space Weather Prediction Center",
     "url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
     "page": "https://www.swpc.noaa.gov/",
     "licence": "US Government work, public domain; credit NOAA SWPC",
     "terms": "https://www.weather.gov/disclaimer"},
    {"id": "spc-outlook", "update": "several times a day", "name": "NOAA Storm Prediction Center",
     "url": "https://www.spc.noaa.gov/products/outlook/day1otlk_cat.nolyr.geojson", "page": "https://www.spc.noaa.gov/products/outlook/",
     "licence": "US Government work, public domain; credit NOAA/NWS SPC", "terms": "https://www.weather.gov/disclaimer"},
    {"id": "hms-smoke", "update": "daily, updated through the day", "name": "NOAA Hazard Mapping System (smoke)", "xml": True, "ext": ".kml",
     "url": "https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/KML/{y}/{m}/hms_smoke{ymd}.kml",
     "page": "https://www.ospo.noaa.gov/Products/land/hms.html",
     "licence": "US Government work, public domain; credit NOAA/NESDIS HMS", "terms": "https://www.ospo.noaa.gov/Products/land/hms.html"},
    {"id": "atd-faa", "update": "every 5 minutes (via Air Travel Desk)", "name": "FAA airport status, via Air Travel Desk",
     "url": "https://www.airtraveldesklive.com/data/status.json", "page": "https://nasstatus.faa.gov/",
     "licence": "FAA data is US Government work, public domain. Read from the public JSON of our sister site Air Travel Desk, with credit.",
     "terms": "https://www.airtraveldesklive.com/about.html"},
    {"id": "ms365", "update": "every 10 minutes (via Is it 364 yet)", "name": "Microsoft 365 public status, via Is it 364 yet",
     "url": "https://www.isit364yet.com/status.json", "page": "https://status.cloud.microsoft/",
     "licence": "Public status feed of the provider, read by our sister project Is it 364 yet, with credit.",
     "terms": "https://www.isit364yet.com/privacy.html"},
    {"id": "openfda-food", "update": "weekly", "name": "FDA food recalls (openFDA)",
     "url": "https://api.fda.gov/food/enforcement.json?search=report_date:[{d30}%20TO%20{d0}]&limit=100&sort=report_date:desc",
     "page": "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts",
     "licence": "openFDA data is CC0 (public domain)", "terms": "https://open.fda.gov/terms/"},
    {"id": "cpsc", "update": "daily", "name": "US Consumer Product Safety Commission recalls",
     "url": "https://www.saferproducts.gov/RestWebServices/Recall?format=json&RecallDateStart={dd14}",
     "page": "https://www.cpsc.gov/Recalls", "licence": "US Government work; headlines and links only",
     "terms": "https://www.cpsc.gov/About-CPSC/Agency-Information/Website-Policies"},
    {"id": "cisa-kev", "update": "several times a week", "name": "CISA Known Exploited Vulnerabilities catalog",
     "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
     "page": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "licence": "CC0 (public domain)",
     "terms": "https://www.cisa.gov/license"},
    {"id": "status-github", "update": "live (provider status page)", "name": "GitHub public status page", "provider": "GitHub",
     "url": "https://www.githubstatus.com/api/v2/summary.json", "page": "https://www.githubstatus.com/",
     "licence": "Provider's public status page; headline and link only", "terms": "https://www.githubstatus.com/"},
    {"id": "status-cloudflare", "update": "live (provider status page)", "name": "Cloudflare public status page", "provider": "Cloudflare",
     "url": "https://www.cloudflarestatus.com/api/v2/summary.json", "page": "https://www.cloudflarestatus.com/",
     "licence": "Provider's public status page; headline and link only", "terms": "https://www.cloudflarestatus.com/"},
    {"id": "status-openai", "update": "live (provider status page)", "name": "OpenAI public status page", "provider": "OpenAI",
     "url": "https://status.openai.com/api/v2/summary.json", "page": "https://status.openai.com/",
     "licence": "Provider's public status page; headline and link only", "terms": "https://status.openai.com/"},
    {"id": "status-atlassian", "update": "live (provider status page)", "name": "Atlassian public status page", "provider": "Atlassian",
     "url": "https://status.atlassian.com/api/v2/summary.json", "page": "https://status.atlassian.com/",
     "licence": "Provider's public status page; headline and link only", "terms": "https://status.atlassian.com/"},
    {"id": "fedreg-presidential", "update": "daily (business days)", "name": "Federal Register: presidential documents",
     "url": "https://www.federalregister.gov/api/v1/documents.json?per_page=15&order=newest&conditions%5Btype%5D%5B%5D=PRESDOCU",
     "page": "https://www.federalregister.gov/presidential-documents", "licence": "US Government work, public domain; headline and link only",
     "terms": "https://www.federalregister.gov/reader-aids/policy"},
    {"id": "fcdo", "update": "as published", "name": "UK Foreign, Commonwealth & Development Office (GOV.UK)", "xml": True,
     "url": "https://www.gov.uk/government/organisations/foreign-commonwealth-development-office.atom",
     "page": "https://www.gov.uk/government/organisations/foreign-commonwealth-development-office",
     "licence": "Open Government Licence v3.0; contains public sector information licensed under the OGL",
     "terms": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"},
    {"id": "eu-press", "update": "as published", "name": "European Commission press corner", "xml": True,
     "url": "https://ec.europa.eu/commission/presscorner/api/rss?language=en",
     "page": "https://ec.europa.eu/commission/presscorner/home/en",
     "licence": "Commission Decision 2011/833/EU on reuse of documents; source credited, headline and link only",
     "terms": "https://commission.europa.eu/legal-notice_en"},
    {"id": "gdelt-doc", "gkg": True, "update": "every 15 minutes", "name": "GDELT Project (outlet headlines)",
     "url": "https://data.gdeltproject.org/gdeltv2/lastupdate.txt",
     "page": "https://www.gdeltproject.org/",
     "licence": "GDELT allows unrestricted use with credit to GDELT. Outlet headlines are shown as links to the outlet, not as our words.",
     "terms": "https://www.gdeltproject.org/about.html#termsofuse"},
    {"id": "tsunami-ak", "update": "when a bulletin is issued", "name": "NOAA National Tsunami Warning Center (Alaska)", "xml": True,
     "url": "https://www.tsunami.gov/events/xml/PAAQAtom.xml", "page": "https://www.tsunami.gov/",
     "licence": "US Government work, public domain; credit NOAA/NWS", "terms": "https://www.weather.gov/disclaimer"},
    {"id": "tsunami-hi", "update": "when a bulletin is issued", "name": "NOAA Pacific Tsunami Warning Center (Hawaii)", "xml": True,
     "url": "https://www.tsunami.gov/events/xml/PHEBAtom.xml", "page": "https://www.tsunami.gov/",
     "licence": "US Government work, public domain; credit NOAA/NWS", "terms": "https://www.weather.gov/disclaimer"},
    {"id": "gdacs", "update": "every few minutes", "name": "GDACS (UN and European Commission)",
     "url": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;FL;VO;DR;WF&alertlevel=Green;Orange;Red",
     "page": "https://www.gdacs.org/",
     "licence": "GDACS terms of use; credit GDACS",
     "terms": "https://www.gdacs.org/About/termsofuse.aspx"},
]


GKG_THEMES = {"ARMEDCONFLICT", "ELECTION", "PROTEST", "TERROR", "LEGISLATION", "EPU_CATS_NATIONAL_SECURITY", "GENERAL_GOVERNMENT"}


def fetch_gkg(files=4):
    """Read the newest GDELT 2.0 GKG files (static, 15 minute batches) and return articles with a page title and a matching theme."""
    import io
    import zipfile
    req = urllib.request.Request("https://data.gdeltproject.org/gdeltv2/lastupdate.txt", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        txt = r.read().decode("utf-8", "replace")
    m = re.search(r"/gdeltv2/(\d{14})\.gkg\.csv\.zip", txt)
    if not m:
        raise ValueError("no gkg file listed")
    t0 = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    arts, seen = [], set()
    for k in range(files):
        ts = (t0 - timedelta(minutes=15 * k)).strftime("%Y%m%d%H%M%S")
        try:
            rq = urllib.request.Request("https://data.gdeltproject.org/gdeltv2/%s.gkg.csv.zip" % ts, headers={"User-Agent": UA})
            with urllib.request.urlopen(rq, timeout=60) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
        except Exception:  # noqa: BLE001
            continue
        for line in z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines():
            f = line.split("\t")
            if len(f) < 27 or f[25]:  # skip machine-translated items
                continue
            tm = re.search(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", f[26], re.S)
            if not tm or not f[4].startswith("http"):
                continue
            themes = {x.split(",")[0] for x in f[7].split(";") if x}
            if not (themes & GKG_THEMES) or f[4] in seen:
                continue
            seen.add(f[4])
            arts.append({"url": f[4], "title": " ".join(tm.group(1).split()), "seendate": f[1][:8] + "T" + f[1][8:] + "Z",
                         "domain": f[3], "sourcecountry": ""})
    return {"articles": arts}


def fetch_json(src, fixtures):
    if src.get("gkg") and not fixtures:
        return fetch_gkg()
    if fixtures:
        with open(os.path.join(fixtures, src["id"] + (src.get("ext", ".xml") if src.get("xml") else ".json")), encoding="utf-8") as f:
            return f.read() if src.get("xml") else json.load(f)
    if "{d0}" in src["url"] or "{dd14}" in src["url"]:
        n = datetime.now(timezone.utc)
        src = dict(src, url=src["url"].format(d0=n.strftime("%Y%m%d"), d30=(n - timedelta(days=30)).strftime("%Y%m%d"),
                                                dd14=(n - timedelta(days=14)).strftime("%Y-%m-%d")))
    if "{ymd}" in src["url"]:
        # HMS publishes one file per day; use today's, and yesterday's when today's is still empty.
        for back in (0, 1):
            d = datetime.now(timezone.utc) - timedelta(days=back)
            u = src["url"].format(y=d.strftime("%Y"), m=d.strftime("%m"), ymd=d.strftime("%Y%m%d"))
            try:
                txt = fetch_json(dict(src, url=u), None)
            except Exception:  # noqa: BLE001
                continue
            if "<Placemark" in txt:
                return txt
        raise ValueError("no HMS file with data")
    req = urllib.request.Request(src["url"], headers={"User-Agent": UA, "Accept": "application/xml, text/xml, */*" if src.get("xml") else "application/json"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace") if src.get("xml") else json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(7 if src.get("slow") else 2 * (attempt + 1))
    raise last


def mk(id_, type_, title, place, lat, lon, when, sev, size, src, url, **extra):
    e = {"id": id_, "type": type_, "title": title, "place": place,
         "lat": None if lat is None else round(lat, 2), "lon": None if lon is None else round(lon, 2),
         "time": iso_utc(when), "severity": sev, "size": size,
         "source": src["name"], "source_id": src["id"], "source_url": url or src["page"]}
    region = extra.pop("region", None)
    e.update(extra)
    e["region"] = region or region_of(lat, lon, place)
    return e


# ---------- parsers: each takes parsed JSON and returns a list of events ----------

def parse_usgs(d, src):
    out = []
    for f in d.get("features", []):
        p = f["properties"]
        if p.get("mag") is None or p.get("type") not in (None, "earthquake"):
            continue
        lon, lat, depth = f["geometry"]["coordinates"][:3]
        mag = float(p["mag"])
        sev = "extreme" if mag >= 7 else "severe" if mag >= 6 else "moderate" if mag >= 5 else "minor"
        pager = p.get("alert")
        if pager == "red":
            sev = "extreme"
        elif pager == "orange" and sev in ("minor", "moderate"):
            sev = "severe"
        when = datetime.fromtimestamp(p["time"] / 1000, timezone.utc)
        e = mk("usgs-" + f["id"], "earthquake", "M %.1f earthquake" % mag, p.get("place") or "Unknown place",
               lat, lon, when, sev, mag, src, p.get("url"),
               detail={"magnitude": round(mag, 1), "depth_km": round(depth), "tsunami_flag": bool(p.get("tsunami")),
                       "felt_reports": p.get("felt"), "pager": p.get("alert")})
        out.append(e)
    return out


def parse_nws(d, src):
    groups = {}
    for f in d.get("features", []):
        p = f["properties"]
        if p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        ugc = (p.get("geocode") or {}).get("UGC") or []
        states = sorted({u[:2] for u in ugc if len(u) >= 2 and u[:2] in STATE_CENTROIDS})
        if not states:
            continue
        st = states[0]
        key = (p["event"], st)
        g = groups.setdefault(key, {"n": 0, "sev": "Severe", "sent": p["sent"], "id": p["id"], "area": p.get("areaDesc", ""), "sender": p.get("senderName", "")})
        g["n"] += 1
        if p.get("severity") == "Extreme":
            g["sev"] = "Extreme"
        if p["sent"] > g["sent"]:
            g["sent"] = p["sent"]
    out = []
    for (ev, st), g in groups.items():
        lat, lon, name = STATE_CENTROIDS[st]
        when = parse_time(g["sent"])
        out.append(mk("nws-%s-%s" % (re.sub(r"\W+", "", ev).lower(), st), "weather", ev, name + ", United States",
                      lat, lon, when, g["sev"].lower(), g["n"], src, "https://www.weather.gov/" + st.lower(),
                      detail={"alerts": g["n"], "state": st, "issuer": g["sender"].split(";")[0],
                              "location_note": "State centre, not the exact area"}))
    return out


def parse_nhc(d, src):
    out = []
    for s in d.get("activeStorms", []):
        try:
            lat, lon = float(s["latitudeNumeric"]), float(s["longitudeNumeric"])
            kt = float(s.get("intensity") or 0)
            when = parse_time(s["lastUpdate"])
        except (KeyError, ValueError, TypeError):
            continue
        mph = round(kt * 1.15078)
        sev = "extreme" if mph >= 111 else "severe" if mph >= 74 else "moderate"
        out.append(mk("nhc-" + s.get("id", s.get("name", "x")).lower(), "storm", "%s %s" % (s.get("classification", "Storm"), s.get("name", "")),
                      "Atlantic or Pacific basin", lat, lon, when, sev, mph, src,
                      "https://www.nhc.noaa.gov/", detail={"wind_mph": mph, "classification": s.get("classification")}))
    return out


EONET_TYPES = {"wildfires": "wildfire", "volcanoes": "volcano", "severeStorms": "storm", "floods": "flood",
               "earthquakes": None, "drought": "drought", "dustHaze": "other", "landslides": "other",
               "tempExtremes": "other", "snow": "other", "seaLakeIce": None, "manmade": None, "waterColor": None}


def parse_eonet(d, src):
    out = []
    for ev in d.get("events", []):
        cat = ev["categories"][0]["id"] if ev.get("categories") else ""
        t = EONET_TYPES.get(cat)
        if not t or not ev.get("geometry"):
            continue
        g = ev["geometry"][-1]
        if g.get("type") != "Point":
            continue
        lon, lat = g["coordinates"][:2]
        when = parse_time(g["date"])
        mag, unit = g.get("magnitudeValue"), g.get("magnitudeUnit")
        sev = "moderate"
        if t == "wildfire" and mag:
            sev = "severe" if mag >= 10000 else "moderate" if mag >= 1000 else "minor"
        if t == "volcano":
            sev = "moderate"
        url = (ev.get("sources") or [{}])[0].get("url") or ev.get("link")
        out.append(mk("eonet-" + ev["id"], t, ev["title"], ev["title"], lat, lon, when, sev, mag or 0, src, url,
                      detail={"magnitude": mag, "unit": unit, "category": cat}))
    return out


GDACS_TYPES = {"TC": "storm", "FL": "flood", "VO": "volcano", "DR": "drought", "WF": "wildfire", "EQ": "earthquake"}
GDACS_SEV = {"Red": "extreme", "Orange": "severe", "Green": "minor"}


def parse_gdacs(d, src):
    out = []
    for f in d.get("features", []):
        p = f["properties"]
        t = GDACS_TYPES.get(p.get("eventtype"))
        if not t or p.get("iscurrent") == "false":
            continue
        # Earthquakes and wildfires come from USGS and EONET; keep only GDACS Orange or Red for them.
        if t in ("earthquake", "wildfire") and p.get("alertlevel") == "Green":
            continue
        if t == "earthquake":
            continue  # USGS covers quakes with better detail
        lon, lat = f["geometry"]["coordinates"][:2]
        sv = p.get("severitydata") or {}
        out.append(mk("gdacs-%s-%s" % (p["eventtype"].lower(), p["eventid"]), t, p.get("name") or t, p.get("country") or "",
                      lat, lon, parse_time(p.get("datemodified") or p["fromdate"]), GDACS_SEV.get(p.get("alertlevel"), "minor"),
                      sv.get("severity") or 0, src, (p.get("url") or {}).get("report"),
                      detail={"alert_level": p.get("alertlevel"), "severity_text": sv.get("severitytext"),
                              "affected_countries": [c.get("countryname") for c in p.get("affectedcountries") or [] if c.get("countryname")][:6]}))
    return out


def parse_volcano(d, src):
    out = []
    for v in d:
        color = (v.get("color_code") or "").upper()
        if color not in ("YELLOW", "ORANGE", "RED"):
            continue
        lat = lon = None
        if not FIXTURE_MODE:
            try:
                info = fetch_json({"id": "x", "url": "https://volcanoes.usgs.gov/hans-public/api/volcano/getVolcano/%s" % v["vnum"]}, None)
                lat, lon = float(info["latitude"]), float(info["longitude"])
            except Exception:  # noqa: BLE001
                pass
        sev = {"RED": "extreme", "ORANGE": "severe", "YELLOW": "moderate"}[color]
        out.append(mk("volcano-" + v["vnum"], "volcano", "%s volcano: alert level %s (%s)" % (v["volcano_name"], (v.get("alert_level") or "").title(), color.title()), v["obs_fullname"], lat, lon,
                      parse_time(v["sent_utc"]), sev, 0, src, v.get("notice_url"),
                      detail={"color_code": color.title(), "alert_level": (v.get("alert_level") or "").title(),
                              "observatory": v["obs_fullname"], "volcano": v["volcano_name"]}))
    return out


def parse_kp(d, src):
    rows = [r for r in d if isinstance(r, dict) and r.get("Kp") is not None]
    if not rows:
        return []
    best = max(rows[-8:], key=lambda r: float(r["Kp"]))  # last 24 hours
    kp = float(best["Kp"])
    if kp < 5:
        return []
    g = int(min(5, kp - 4))
    sev = "extreme" if g >= 4 else "severe" if g >= 3 else "moderate"
    return [mk("swpc-kp-" + best["time_tag"], "space", "Geomagnetic storm, G%d level" % g, "Global (aurora possible at high latitudes)",
               None, None, parse_time(best["time_tag"]), sev, kp, src, "https://www.swpc.noaa.gov/",
               detail={"kp": kp, "g_scale": g})]


def parse_tsunami(xml_text, src):
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    out = []
    for ent in root.findall("a:entry", ns):
        title = " ".join((ent.findtext("a:title", "", ns) or "").split())
        low = title.lower()
        if not re.search(r"warning|watch|advisory", low) or "information" in low or "cancel" in low:
            continue
        when = parse_time(ent.findtext("a:updated", "", ns))
        sev = "extreme" if "warning" in low else "severe" if "watch" in low else "moderate"
        out.append(mk("tsunami-" + re.sub(r"\W+", "", ent.findtext("a:id", title, ns))[-24:], "tsunami", title.title(),
                      src["name"], None, None, when, sev, 0, src, "https://www.tsunami.gov/",
                      detail={"bulletin": title.title(), "centre": src["name"]}))
    return out


SPC_RISK = {"SLGT": ("Slight", "minor"), "ENH": ("Enhanced", "moderate"), "MDT": ("Moderate", "severe"), "HIGH": ("High", "extreme")}


def _coords(geom):
    def walk(c):
        if c and isinstance(c[0], (int, float)):
            yield c
        else:
            for x in c:
                yield from walk(x)
    return list(walk(geom["coordinates"]))


def parse_spc(d, src):
    out = []
    for f in d.get("features", []):
        p = f["properties"]
        if p.get("LABEL") not in SPC_RISK or not f.get("geometry"):
            continue
        name, sev = SPC_RISK[p["LABEL"]]
        pts = _coords(f["geometry"])
        lon = (min(c[0] for c in pts) + max(c[0] for c in pts)) / 2
        lat = (min(c[1] for c in pts) + max(c[1] for c in pts)) / 2
        out.append(mk("spc-day1-" + p["LABEL"].lower(), "weather", "Severe thunderstorm outlook: %s risk" % name,
                      "United States (outlook area)", lat, lon, parse_time(p["ISSUE_ISO"]), sev, 0, src,
                      "https://www.spc.noaa.gov/products/outlook/day1otlk.html",
                      detail={"risk": name, "valid_until": p["EXPIRE_ISO"][:16].replace("T", " ") + " UTC",
                              "location_note": "Centre of the risk area, not a point forecast"}))
    return out


def parse_hms(kml, src):
    import xml.etree.ElementTree as ET
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    groups = {}
    for pm in ET.fromstring(kml).iter("{http://www.opengis.net/kml/2.2}Placemark"):
        desc = pm.findtext("k:description", "", ns)
        dm = re.search(r"Density: (\w+)", desc)
        em = re.search(r"End Time: (\d{4})(\d{3}) (\d{2})(\d{2})UTC", desc)
        co = pm.findtext(".//k:coordinates", "", ns).split()
        if not dm or not em or not co or dm.group(1) not in ("Medium", "Heavy"):
            continue
        pts = [tuple(float(v) for v in c.split(",")[:2]) for c in co]
        end = datetime(int(em.group(1)), 1, 1, int(em.group(3)), int(em.group(4)), tzinfo=timezone.utc) + timedelta(days=int(em.group(2)) - 1)
        box = (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
        g = groups.setdefault(dm.group(1), {"n": 0, "end": end, "area": -1, "c": None})
        g["n"] += 1
        g["end"] = max(g["end"], end)
        area = (box[1] - box[0]) * (box[3] - box[2])
        if area > g["area"]:
            g["area"], g["c"] = area, ((box[2] + box[3]) / 2, (box[0] + box[1]) / 2)
    out = []
    for dens, g in groups.items():
        out.append(mk("hms-smoke-" + dens.lower(), "smoke", "%s smoke plumes seen by satellite" % dens, "North America (largest plume shown)",
                      g["c"][0], g["c"][1], g["end"], "moderate" if dens == "Heavy" else "minor", g["n"], src,
                      "https://www.ospo.noaa.gov/Products/land/hms.html",
                      detail={"density": dens, "plumes": g["n"], "location_note": "Centre of the largest plume, not every plume"}))
    return out


AIRPORT_NAMES = {'ATL': 'Atlanta, GA', 'LAX': 'Los Angeles, CA', 'ORD': "Chicago O'Hare, IL", 'DFW': 'Dallas-Fort Worth, TX', 'DEN': 'Denver, CO', 'JFK': 'New York JFK, NY', 'SFO': 'San Francisco, CA', 'SEA': 'Seattle-Tacoma, WA', 'LAS': 'Las Vegas, NV', 'MCO': 'Orlando, FL', 'EWR': 'Newark, NJ', 'CLT': 'Charlotte, NC', 'PHX': 'Phoenix, AZ', 'IAH': 'Houston Bush, TX', 'MIA': 'Miami, FL', 'BOS': 'Boston, MA', 'MSP': 'Minneapolis-St. Paul, MN', 'FLL': 'Fort Lauderdale, FL', 'DTW': 'Detroit, MI', 'PHL': 'Philadelphia, PA', 'LGA': 'New York LaGuardia, NY', 'BWI': 'Baltimore-Washington, MD', 'SLC': 'Salt Lake City, UT', 'SAN': 'San Diego, CA', 'IAD': 'Washington Dulles, VA', 'DCA': 'Washington National, VA', 'MDW': 'Chicago Midway, IL', 'TPA': 'Tampa, FL', 'HNL': 'Honolulu, HI', 'PDX': 'Portland, OR', 'STL': 'St. Louis, MO', 'BNA': 'Nashville, TN', 'AUS': 'Austin, TX', 'MSY': 'New Orleans, LA', 'RDU': 'Raleigh-Durham, NC', 'SMF': 'Sacramento, CA', 'SJC': 'San Jose, CA', 'OAK': 'Oakland, CA', 'SNA': 'Santa Ana (Orange County), CA', 'HOU': 'Houston Hobby, TX', 'DAL': 'Dallas Love Field, TX', 'MCI': 'Kansas City, MO', 'CLE': 'Cleveland, OH', 'PIT': 'Pittsburgh, PA', 'IND': 'Indianapolis, IN', 'CMH': 'Columbus, OH', 'CVG': 'Cincinnati, OH', 'SAT': 'San Antonio, TX', 'SJU': 'San Juan, PR', 'ANC': 'Anchorage, AK', 'BUR': 'Burbank, CA', 'ONT': 'Ontario, CA', 'PBI': 'West Palm Beach, FL', 'RSW': 'Fort Myers, FL', 'JAX': 'Jacksonville, FL', 'BDL': 'Hartford, CT', 'MKE': 'Milwaukee, WI', 'ABQ': 'Albuquerque, NM', 'OMA': 'Omaha, NE', 'BUF': 'Buffalo, NY', 'RIC': 'Richmond, VA', 'OKC': 'Oklahoma City, OK', 'MEM': 'Memphis, TN', 'SDF': 'Louisville, KY', 'TUS': 'Tucson, AZ', 'ELP': 'El Paso, TX', 'BOI': 'Boise, ID', 'GEG': 'Spokane, WA', 'PVD': 'Providence, RI', 'CHS': 'Charleston, SC', 'ORF': 'Norfolk, VA', 'DSM': 'Des Moines, IA', 'GRR': 'Grand Rapids, MI', 'LIT': 'Little Rock, AR', 'ALB': 'Albany, NY', 'SYR': 'Syracuse, NY', 'ROC': 'Rochester, NY', 'MHT': 'Manchester, NH', 'PWM': 'Portland, ME', 'BTV': 'Burlington, VT', 'ICT': 'Wichita, KS', 'TUL': 'Tulsa, OK', 'COS': 'Colorado Springs, CO', 'RNO': 'Reno, NV', 'PSP': 'Palm Springs, CA', 'SBA': 'Santa Barbara, CA', 'MSN': 'Madison, WI', 'FAT': 'Fresno, CA', 'OGG': 'Maui, HI', 'KOA': 'Kona, HI', 'LIH': 'Kauai, HI', 'GUM': 'Guam'}


FAA_KIND = {"ground_stop": ("Ground stop", "severe"), "closure": ("Airport closed", "severe"),
            "ground_delay": ("Ground delay program", "moderate"), "delay": ("Delays", "moderate")}


def delay_minutes(text):
    """'2 hours and 46 minutes' -> 166. Numbers pass through. Anything else -> None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    h = re.search(r"(\d+)\s*hour", str(text))
    m = re.search(r"(\d+)\s*min", str(text))
    if not (h or m):
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def parse_faa(d, src):
    airports = {}
    try:
        if FIXTURE_MODE:
            with open(os.path.join(FIXTURE_DIR, "atd-airports.json"), encoding="utf-8") as f:
                airports = json.load(f)
        else:
            airports = fetch_json({"id": "x", "url": "https://www.airtraveldesklive.com/data/airports.json"}, None)
        airports = airports.get("airports", airports)
    except Exception:  # noqa: BLE001
        airports = {}
    when = parse_time(d["updated_utc"])
    out = []
    for ev in d.get("events", []):
        label, sev = FAA_KIND.get(ev.get("kind"), (None, None))
        if not label:
            continue
        ap = airports.get(ev["code"]) or {}
        name = ap.get("name") or AIRPORT_NAMES.get(ev["code"]) or ev.get("name") or ev["code"]
        mins = delay_minutes(ev.get("avg")) or delay_minutes(ev.get("max")) or 0
        detail = {"kind": label, "airport_code": ev["code"], "reason": ev.get("reason") or "",
                  "avg_delay_min": delay_minutes(ev.get("avg")), "max_delay_min": delay_minutes(ev.get("max")),
                  "avg_delay_text": str(ev["avg"]) if ev.get("avg") else "", "max_delay_text": str(ev["max"]) if ev.get("max") else "",
                  "until": ev.get("end_time") or "",
                  "faa_status": ev.get("status") or ""}
        out.append(mk("faa-%s-%s" % (ev["kind"], ev["code"]), "transport", "%s at %s" % (label, ev["code"]),
                      name if name != ev["code"] else "Airport " + ev["code"], ap.get("lat"), ap.get("lon"), when, sev, mins, src,
                      "https://nasstatus.faa.gov/", detail=detail))
    return out


def parse_ms365(d, src):
    out = []
    cur = d.get("current")
    if cur:
        out.append(mk("ms365-" + cur["id"], "outage", "Microsoft 365 service incident", "Microsoft 365 (consumer services)", None, None,
                      parse_time(cur["start"]), "severe", 0, src, "https://status.cloud.microsoft/",
                      detail={"status": d.get("status") or "", "since": cur["start"][:16].replace("T", " ") + " UTC", "open": True}))
    else:
        for inc in d.get("incidents", [])[:1]:
            end = parse_time(inc["end"]) if inc.get("end") else None
            if end:
                out.append(mk("ms365-" + inc["id"], "outage", "Microsoft 365 incident ended", "Microsoft 365 (consumer services)", None, None,
                              end, "minor", inc.get("hours") or 0, src, "https://status.cloud.microsoft/",
                              detail={"status": "Service restored", "hours": inc.get("hours"), "open": False,
                                      "started": inc["start"][:16].replace("T", " ") + " UTC"}))
    return out


def parse_openfda(d, src):
    out = []
    for r in d.get("results", []):
        cls = r.get("classification") or ""
        sev = {"Class I": "severe", "Class II": "moderate"}.get(cls, "minor")
        if cls == "Class III":
            continue
        prod = " ".join((r.get("product_description") or "").split())[:110]
        when = datetime.strptime(r["report_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
        out.append(mk("fda-" + re.sub(r"\W+", "", r.get("recall_number", "x")), "recall", "FDA %s food recall" % cls, r.get("recalling_firm") or "",
                      None, None, when, sev, 0, src, "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts",
                      detail={"class": cls, "product": prod, "firm": r.get("recalling_firm") or "", "reason": " ".join((r.get("reason_for_recall") or "").split())[:160],
                              "recall_number": r.get("recall_number") or "", "distribution": " ".join((r.get("distribution_pattern") or "").split())[:100]}))
    return out


def parse_cpsc(d, src):
    out = []
    for r in d:
        title = " ".join((r.get("Title") or "").split())[:140]
        when = parse_time(r["RecallDate"])
        out.append(mk("cpsc-" + str(r["RecallNumber"]), "recall", "CPSC recall: " + title, "United States", None, None, when, "moderate", 0, src,
                      r.get("URL"), detail={"recall_number": str(r["RecallNumber"]), "headline": title}))
    return out


def parse_kev(d, src):
    now_d = datetime.now(timezone.utc) if not FIXTURE_MODE else datetime(2026, 11, 14, tzinfo=timezone.utc)
    recent = [v for v in d.get("vulnerabilities", []) if (now_d - datetime.strptime(v["dateAdded"], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days <= 3]
    if not recent:
        return []
    last = max(v["dateAdded"] for v in recent)
    names = ", ".join(sorted({v["vendorProject"] for v in recent}))[:140]
    return [mk("cisa-kev-" + last, "cyber", "CISA added %d known exploited vulnerabilities" % len(recent), "Software vendors: " + names, None, None,
               datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=timezone.utc), "moderate", len(recent), src,
               "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
               detail={"count": len(recent), "date_added": last, "vendors": names, "catalog_total": d.get("count")})]


IMPACT = {"critical": "extreme", "major": "severe", "minor": "moderate"}


def parse_statuspage(d, src):
    out = []
    for inc in d.get("incidents", []):
        if inc.get("status") == "resolved":
            continue
        sev = IMPACT.get(inc.get("impact"), "minor")
        name = " ".join((inc.get("name") or "").split())[:120]
        title = name if name.lower().startswith(src["provider"].lower()) else "%s: %s" % (src["provider"], name)
        out.append(mk("status-%s-%s" % (src["id"].split("-")[1], inc["id"]), "outage", title, src["provider"] + " status page",
                      None, None, parse_time(inc.get("created_at") or inc.get("started_at")), sev, 0, src,
                      inc.get("shortlink") or src["page"],
                      detail={"provider": src["provider"], "incident": name, "status": (inc.get("status") or "").replace("_", " "),
                              "impact": inc.get("impact") or "", "open": True}))
    return out


def parse_fedreg(d, src):
    out = []
    for r in d.get("results", []):
        title = " ".join((r.get("title") or "").split())[:150]
        when = datetime.strptime(r["publication_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        out.append(mk("fr-" + r["document_number"], "notice", title, "Federal Register, presidential documents", None, None, when,
                      "moderate", 0, src, r.get("html_url"),
                      detail={"title": title, "document_number": r["document_number"], "published": r["publication_date"],
                              "kind": r.get("type") or "Presidential Document"}))
    return out


def _entries(xml_text):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_text)
    a = "{http://www.w3.org/2005/Atom}"
    out = []
    for ent in root.iter(a + "entry"):
        link = ent.find(a + "link")
        out.append({"title": " ".join((ent.findtext(a + "title") or "").split()), "url": link.get("href") if link is not None else None,
                    "time": ent.findtext(a + "updated"), "id": ent.findtext(a + "id") or ""})
    for it in root.iter("item"):
        out.append({"title": " ".join((it.findtext("title") or "").split()), "url": it.findtext("link"),
                    "time": it.findtext("pubDate"), "id": it.findtext("guid") or it.findtext("link") or ""})
    return out


def _parse_any_time(t):
    from email.utils import parsedate_to_datetime
    try:
        return parse_time(t)
    except ValueError:
        return parsedate_to_datetime(t).astimezone(timezone.utc)


def parse_statements(xml_text, src, party, place):
    out = []
    for e in _entries(xml_text)[:6]:
        if not e["title"] or not (e["url"] or "").startswith("https://"):
            continue
        out.append(mk("stmt-%s-%s" % (src["id"], re.sub(r"\W+", "", e["id"])[-30:]), "statement", "%s: %s" % (party, e["title"][:150]), place,
                      None, None, _parse_any_time(e["time"]), "minor", 0, src, e["url"], region="World",
                      detail={"party": party, "headline": e["title"][:150], "published": iso_utc(_parse_any_time(e["time"]))[:16].replace("T", " ") + " UTC"}))
    return out


def parse_fcdo(x, src):
    return parse_statements(x, src, "UK Foreign Office", "United Kingdom (government)")


def parse_eu(x, src):
    return parse_statements(x, src, "European Commission", "European Union (institution)")


STOP = set("with from that this over after have will been were what into about their they them than says said news live amid more most year week today".split())


def _toks(title):
    t = re.split(r" [-|\u2013\u2014] ", title)[0].lower()
    return {w for w in re.findall(r"[a-z]{4,}", t) if w not in STOP}


def parse_gdelt(d, src):
    arts = d.get("articles", []) if isinstance(d, dict) else []
    clusters = []
    for a in arts:
        tk = _toks(a.get("title", ""))
        if len(tk) < 3 or not (a.get("url") or "").startswith("http"):
            continue
        for c in clusters:
            if len(tk & c["tk"]) / float(len(tk | c["tk"])) >= 0.45:
                c["arts"].append(a)
                c["tk"] |= tk
                break
        else:
            clusters.append({"tk": set(tk), "arts": [a]})
    out = []
    for c in clusters:
        by_domain = {}
        for a in c["arts"]:
            by_domain.setdefault(a["domain"], a)
        if len(by_domain) < 2:
            continue
        picked, seen_c = [], set()
        for a in sorted(by_domain.values(), key=lambda x: x["seendate"]):
            if a.get("sourcecountry") not in seen_c:
                picked.append(a)
                seen_c.add(a.get("sourcecountry"))
        for a in sorted(by_domain.values(), key=lambda x: x["seendate"]):
            if a not in picked:
                picked.append(a)
        picked = picked[:3]
        first = min(by_domain.values(), key=lambda x: x["seendate"])
        when = datetime.strptime(first["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        title = " ".join(picked[0]["title"].split())[:140]
        names = ", ".join(a["domain"] for a in picked)
        e = mk("gdelt-" + re.sub(r"\W+", "", sorted(c["tk"])[0] + sorted(c["tk"])[-1] + first["seendate"])[:40], "headline",
               "Headline: \u201c%s\u201d" % title, "Reported by %d outlets" % len(by_domain), None, None, when, "minor", len(by_domain), src,
               picked[0]["url"], region="World",
               detail={"outlets": len(by_domain), "outlet_names": names, "headline": title, "first_seen": iso_utc(when)[:16].replace("T", " ") + " UTC"})
        e["links"] = [{"label": a["domain"], "title": " ".join(a["title"].split())[:140], "url": a["url"]} for a in picked]
        out.append(e)
    out.sort(key=lambda e: -e["size"])
    return out[:12]


PARSERS = {"fcdo": parse_fcdo, "eu-press": parse_eu, "gdelt-doc": parse_gdelt, "fedreg-presidential": parse_fedreg, "openfda-food": parse_openfda, "cpsc": parse_cpsc, "cisa-kev": parse_kev,
           "status-github": parse_statuspage, "status-cloudflare": parse_statuspage, "status-openai": parse_statuspage, "status-atlassian": parse_statuspage, "atd-faa": parse_faa, "ms365": parse_ms365, "hms-smoke": parse_hms, "spc-outlook": parse_spc, "tsunami-ak": parse_tsunami, "tsunami-hi": parse_tsunami, "usgs-volcano": parse_volcano, "swpc-kp": parse_kp, "usgs-quakes": parse_usgs, "nws-alerts": parse_nws, "nhc": parse_nhc, "eonet": parse_eonet, "gdacs": parse_gdacs}


def dedupe(events):
    """Drop a later event that matches an earlier one of the same type within 150 km and 12 h."""
    kept = []
    for e in sorted(events, key=lambda x: (x["source_id"] != "usgs-quakes", x["source_id"] != "nhc", x["id"])):
        dup = False
        for k in kept:
            if k["type"] == e["type"] and e["lat"] is not None and k["lat"] is not None and e["type"] in ("storm", "volcano", "flood"):
                if haversine_km(k["lat"], k["lon"], e["lat"], e["lon"]) < 150 and \
                   abs((parse_time(k["time"]) - parse_time(e["time"])).total_seconds()) < 12 * 3600:
                    dup = True
                    break
        if not dup:
            kept.append(e)
    return kept


def build(fixtures=None, now=None):
    global FIXTURE_MODE, FIXTURE_DIR
    FIXTURE_MODE = bool(fixtures)
    FIXTURE_DIR = fixtures
    now = now or datetime.now(timezone.utc)
    events, status = [], []
    for src in SOURCES:
        rec = {"id": src["id"], "update": src.get("update", ""), "url": src["url"].split("{")[0].split("?")[0], "name": src["name"], "page": src["page"], "licence": src["licence"], "terms": src["terms"],
               "checked": iso_utc(now), "ok": False, "count": 0}
        try:
            evs = PARSERS[src["id"]](fetch_json(src, fixtures), src)
            rec["ok"], rec["count"] = True, len(evs)
            events += evs
            if src["id"] == "gdelt-doc" and evs and OUT_DIR:
                with open(os.path.join(OUT_DIR, "gdelt-last.json"), "w", encoding="utf-8") as f:
                    json.dump({"saved": iso_utc(now), "events": evs}, f, separators=(",", ":"))
        except Exception as e:  # noqa: BLE001
            rec["error"] = type(e).__name__
            if src["id"] == "gdelt-doc" and OUT_DIR:
                # GDELT limits requests per address. Keep the last good groups for up to 3 hours, and say so.
                try:
                    with open(os.path.join(OUT_DIR, "gdelt-last.json"), encoding="utf-8") as f:
                        last = json.load(f)
                    if (now - parse_time(last["saved"])).total_seconds() < 3 * 3600:
                        events += last["events"]
                        rec["count"] = len(last["events"])
                        rec["note"] = "Rate-limited; showing the last good groups from %s" % last["saved"]
                except (OSError, ValueError, KeyError):
                    pass
        status.append(rec)
    def fresh_enough(e):
        age = MAX_AGE_LONG_H if e["type"] in ("wildfire", "volcano", "drought", "flood", "recall", "notice") else MAX_AGE_H
        t = parse_time(e["time"])
        return now - timedelta(hours=age) <= t <= now + timedelta(hours=1)
    events = [e for e in events if fresh_enough(e)]
    events = dedupe(events)
    good = []
    for e in events:
        try:
            e["score"] = score_event(e, now)
            e["summary"] = summarize(e)
            good.append(e)
        except Exception as ex:  # noqa: BLE001
            # One malformed item must never stop the data job. Drop it, and say which one.
            print("dropped %s: %s %s" % (e.get("id"), type(ex).__name__, ex), file=sys.stderr)
    events = good
    events.sort(key=lambda e: -e["score"])
    # Diversity: repeated US warnings of one kind drop 10 points per earlier copy, so they do not fill the top of the list.
    seen = {}
    for e in events:
        if e["type"] in ("weather", "recall"):
            key = e["title"] if e["type"] == "weather" else "recall"
            n = seen.get(key, 0)
            seen[key] = n + 1
            e["score"] = round(max(0, e["score"] - (10 if e["type"] == "weather" else 3) * n), 1)
    events.sort(key=lambda e: -e["score"])
    return events, status


def track_seen(events, out_dir, now):
    """Add first_seen to each event, remember it in data/seen.json, and append one line to data/log.jsonl."""
    path = os.path.join(out_dir, "seen.json")
    try:
        with open(path, encoding="utf-8") as f:
            seen = json.load(f)
        first_run = False
    except (OSError, ValueError):
        seen, first_run = {}, True
    new_ids = []
    for e in events:
        if e["id"] in seen:
            e["first_seen"] = seen[e["id"]]
        else:
            # On the first run there is no history: use the event time, so nothing is falsely called new.
            e["first_seen"] = e["time"] if first_run else iso_utc(now)
            seen[e["id"]] = e["first_seen"]
            if not first_run:
                new_ids.append(e["id"])
    keep = {e["id"] for e in events}
    seen = {k: v for k, v in seen.items() if k in keep}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seen, f, separators=(",", ":"))
    log = os.path.join(out_dir, "log.jsonl")
    lines = []
    try:
        with open(log, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        pass
    lines.append(json.dumps({"t": iso_utc(now), "count": len(events), "new": new_ids,
                             "by_type": {t: sum(1 for e in events if e["type"] == t) for t in sorted({e["type"] for e in events})}},
                            separators=(",", ":")))
    with open(log, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[-1100:]) + "\n")  # about 7 days at one run per 10 minutes
    return new_ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--fixtures")
    a = ap.parse_args()
    global OUT_DIR
    OUT_DIR = a.out
    os.makedirs(a.out, exist_ok=True)
    now = datetime.now(timezone.utc)
    events, status = build(a.fixtures, now)
    os.makedirs(a.out, exist_ok=True)
    prev = os.path.join(a.out, "events.json")
    if not events and os.path.exists(prev):
        print("No events from any source; keeping the previous file", file=sys.stderr)
        return 0
    track_seen(events, a.out, now)
    if not a.fixtures:
        from tools import context as ctxmod
        n = ctxmod.add_context(events, now, os.path.join(a.out, "context-cache.json"))
        print("context on %d events" % n)
    with open(prev, "w", encoding="utf-8") as f:
        json.dump({"generated": iso_utc(now), "count": len(events), "events": events}, f, separators=(",", ":"))
    with open(os.path.join(a.out, "sources.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": iso_utc(now), "sources": status}, f, indent=1)
    print("events=%d sources_ok=%d/%d" % (len(events), sum(s["ok"] for s in status), len(status)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
