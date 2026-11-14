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
    {"id": "usgs-volcano", "name": "USGS Volcano Hazards Program",
     "url": "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes",
     "page": "https://volcanoes.usgs.gov/",
     "licence": "US Government work, public domain; credit USGS",
     "terms": "https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits"},
    {"id": "swpc-kp", "name": "NOAA Space Weather Prediction Center",
     "url": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
     "page": "https://www.swpc.noaa.gov/",
     "licence": "US Government work, public domain; credit NOAA SWPC",
     "terms": "https://www.weather.gov/disclaimer"},
    {"id": "tsunami-ak", "name": "NOAA National Tsunami Warning Center (Alaska)", "xml": True,
     "url": "https://www.tsunami.gov/events/xml/PAAQAtom.xml", "page": "https://www.tsunami.gov/",
     "licence": "US Government work, public domain; credit NOAA/NWS", "terms": "https://www.weather.gov/disclaimer"},
    {"id": "tsunami-hi", "name": "NOAA Pacific Tsunami Warning Center (Hawaii)", "xml": True,
     "url": "https://www.tsunami.gov/events/xml/PHEBAtom.xml", "page": "https://www.tsunami.gov/",
     "licence": "US Government work, public domain; credit NOAA/NWS", "terms": "https://www.weather.gov/disclaimer"},
    {"id": "gdacs", "name": "GDACS (UN and European Commission)",
     "url": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;FL;VO;DR;WF&alertlevel=Green;Orange;Red",
     "page": "https://www.gdacs.org/",
     "licence": "GDACS terms of use; credit GDACS",
     "terms": "https://www.gdacs.org/About/termsofuse.aspx"},
]


def fetch_json(src, fixtures):
    if fixtures:
        with open(os.path.join(fixtures, src["id"] + (".xml" if src.get("xml") else ".json")), encoding="utf-8") as f:
            return f.read() if src.get("xml") else json.load(f)
    req = urllib.request.Request(src["url"], headers={"User-Agent": UA, "Accept": "application/json"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace") if src.get("xml") else json.load(r)
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
        out.append(mk("volcano-" + v["vnum"], "volcano", "%s volcano" % v["volcano_name"], v["obs_fullname"], lat, lon,
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


PARSERS = {"tsunami-ak": parse_tsunami, "tsunami-hi": parse_tsunami, "usgs-volcano": parse_volcano, "swpc-kp": parse_kp, "usgs-quakes": parse_usgs, "nws-alerts": parse_nws, "nhc": parse_nhc, "eonet": parse_eonet, "gdacs": parse_gdacs}


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
    global FIXTURE_MODE
    FIXTURE_MODE = bool(fixtures)
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
    now = datetime.now(timezone.utc)
    events, status = build(a.fixtures, now)
    os.makedirs(a.out, exist_ok=True)
    prev = os.path.join(a.out, "events.json")
    if not events and os.path.exists(prev):
        print("No events from any source; keeping the previous file", file=sys.stderr)
        return 0
    track_seen(events, a.out, now)
    with open(prev, "w", encoding="utf-8") as f:
        json.dump({"generated": iso_utc(now), "count": len(events), "events": events}, f, separators=(",", ":"))
    with open(os.path.join(a.out, "sources.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": iso_utc(now), "sources": status}, f, indent=1)
    print("events=%d sources_ok=%d/%d" % (len(events), sum(s["ok"] for s in status), len(status)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
