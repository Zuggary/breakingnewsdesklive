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

UA = "breakingnewsdesklive/1.0 (+https://breakingnewsdesklive.com; independent alert aggregator)"
MAX_AGE_H = 72
MAX_AGE_LONG_H = 168  # open fires, floods and volcanoes stay listed for 7 days

SOURCES = [
    {"id": "usgs-quakes", "name": "USGS Earthquake Hazards Program",
     "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson",
     "page": "https://earthquake.usgs.gov/earthquakes/map/",
     "licence": "US Government work, public domain; credit USGS",
     "terms": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"},
    {"id": "nws-alerts", "name": "US National Weather Service",
     "url": "https://api.weather.gov/alerts/active?status=actual&severity=Extreme,Severe",
     "page": "https://www.weather.gov/alerts",
     "licence": "US Government work, public domain; credit NOAA/NWS",
     "terms": "https://www.weather.gov/disclaimer"},
    {"id": "nhc", "name": "NOAA National Hurricane Center",
     "url": "https://www.nhc.noaa.gov/CurrentStorms.json",
     "page": "https://www.nhc.noaa.gov/",
     "licence": "US Government work, public domain; credit NOAA/NHC",
     "terms": "https://www.weather.gov/disclaimer"},
    {"id": "eonet", "name": "NASA EONET",
     "url": "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=200",
     "page": "https://eonet.gsfc.nasa.gov/",
     "licence": "NASA open data; credit NASA EONET and the original source",
     "terms": "https://www.nasa.gov/nasa-brand-center/images-and-media/"},
    {"id": "gdacs", "name": "GDACS (UN and European Commission)",
     "url": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;FL;VO;DR;WF&alertlevel=Green;Orange;Red",
     "page": "https://www.gdacs.org/",
     "licence": "GDACS terms of use; credit GDACS",
     "terms": "https://www.gdacs.org/About/termsofuse.aspx"},
]


def fetch_json(src, fixtures):
    if fixtures:
        with open(os.path.join(fixtures, src["id"] + ".json"), encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(src["url"], headers={"User-Agent": UA, "Accept": "application/json"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def mk(id_, type_, title, place, lat, lon, when, sev, size, src, url, **extra):
    e = {"id": id_, "type": type_, "title": title, "place": place,
         "lat": None if lat is None else round(lat, 2), "lon": None if lon is None else round(lon, 2),
         "time": iso_utc(when), "severity": sev, "size": size,
         "source": src["name"], "source_id": src["id"], "source_url": url or src["page"]}
    e.update(extra)
    e["region"] = region_of(lat, lon, place)
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


PARSERS = {"usgs-quakes": parse_usgs, "nws-alerts": parse_nws, "nhc": parse_nhc, "eonet": parse_eonet, "gdacs": parse_gdacs}


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
    now = now or datetime.now(timezone.utc)
    events, status = [], []
    for src in SOURCES:
        rec = {"id": src["id"], "name": src["name"], "page": src["page"], "licence": src["licence"], "terms": src["terms"],
               "checked": iso_utc(now), "ok": False, "count": 0}
        try:
            evs = PARSERS[src["id"]](fetch_json(src, fixtures), src)
            rec["ok"], rec["count"] = True, len(evs)
            events += evs
        except Exception as e:  # noqa: BLE001
            rec["error"] = type(e).__name__
        status.append(rec)
    def fresh_enough(e):
        age = MAX_AGE_LONG_H if e["type"] in ("wildfire", "volcano", "drought", "flood") else MAX_AGE_H
        t = parse_time(e["time"])
        return now - timedelta(hours=age) <= t <= now + timedelta(hours=1)
    events = [e for e in events if fresh_enough(e)]
    events = dedupe(events)
    for e in events:
        e["score"] = score_event(e, now)
        e["summary"] = summarize(e)
    events.sort(key=lambda e: -e["score"])
    # Diversity: repeated US warnings of one kind drop 10 points per earlier copy, so they do not fill the top of the list.
    seen = {}
    for e in events:
        if e["type"] == "weather":
            n = seen.get(e["title"], 0)
            seen[e["title"]] = n + 1
            e["score"] = round(max(0, e["score"] - 10 * n), 1)
    events.sort(key=lambda e: -e["score"])
    return events, status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--fixtures")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    events, status = build(a.fixtures, now)
    os.makedirs(a.out, exist_ok=True)
    prev = os.path.join(a.out, "events.json")
    if not events and os.path.exists(prev):
        print("No events from any source; keeping the previous file", file=sys.stderr)
        return 0
    with open(prev, "w", encoding="utf-8") as f:
        json.dump({"generated": iso_utc(now), "count": len(events), "events": events}, f, separators=(",", ":"))
    with open(os.path.join(a.out, "sources.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": iso_utc(now), "sources": status}, f, indent=1)
    print("events=%d sources_ok=%d/%d" % (len(events), sum(s["ok"] for s in status), len(status)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
