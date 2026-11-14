"""Context for events (GD4 stage 2): Wikipedia summary (CC BY-SA 4.0), Commons image with licence and author, NASA GIBS satellite tile.

Rules: exact-title matches only; every item carries its credit; an item that fails validate_item() is dropped.
Network calls happen in the data job, not in visitors' browsers. Only the images are loaded by visitors' browsers.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "breakingnewsdesklive/1.0 (+https://breakingnewsdesklive.com/about.html)"
MAX_EVENTS = 25
CACHE_DAYS = 7
BAD_IMAGE = re.compile(r"flag|seal|coat[_ ]of|logo|emblem|insignia|banner|map[_ ]of|locator", re.I)
ALLOWED_LICENCE = re.compile(r"^(public domain|pd[- ]|cc0|cc by (\d\.\d|\d)\b)", re.I)  # CC BY only; CC BY-SA is excluded


def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def licence_ok(short):
    s = (short or "").strip()
    if re.match(r"^cc by-sa", s, re.I):
        return False
    return bool(ALLOWED_LICENCE.match(s))


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def titles_for(e):
    """Exact Wikipedia titles worth trying for an event. Conservative on purpose."""
    d, t, out = e.get("detail") or {}, e["type"], []
    if t == "volcano" and d.get("volcano"):
        out.append(("volcano", d["volcano"]))
        out.append(("volcano", d["volcano"] + " (volcano)"))
    elif t == "weather" and d.get("state"):
        out.append(("region", e["place"].split(",")[0]))
    elif t == "earthquake" and "," in e["place"]:
        out.append(("region", e["place"].split(",")[-1].strip()))
    return out


def good_match(kind, summ):
    if not summ or summ.get("type") != "standard":
        return False
    desc = ((summ.get("description") or "") + " " + (summ.get("extract") or "")[:300]).lower()
    if kind == "volcano":
        return "volcan" in desc
    if kind == "region":
        return bool(re.search(r"country|republic|kingdom|u\.s\. state|state of|territory|island|nation|province", desc))
    return False


def wiki_summary(title, get=get_json):
    return get("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"), safe="()_,"))


def page_image_name(title, get=get_json):
    q = "https://en.wikipedia.org/w/api.php?action=query&titles=%s&prop=pageimages&piprop=name&format=json&redirects=1" % urllib.parse.quote(title)
    pages = get(q).get("query", {}).get("pages", {})
    for p in pages.values():
        return p.get("pageimage")
    return None


def commons_credit(fname, get=get_json):
    q = ("https://commons.wikimedia.org/w/api.php?action=query&titles=File:%s&prop=imageinfo&iiprop=extmetadata&format=json"
         % urllib.parse.quote(fname))
    for p in get(q).get("query", {}).get("pages", {}).values():
        md = ((p.get("imageinfo") or [{}])[0]).get("extmetadata") or {}
        lic = (md.get("LicenseShortName") or {}).get("value", "")
        author = strip_tags((md.get("Artist") or {}).get("value", ""))
        if licence_ok(lic) and author:
            return {"src": "https://commons.wikimedia.org/wiki/Special:FilePath/%s?width=640" % urllib.parse.quote(fname),
                    "author": author[:120], "license": lic,
                    "credit_url": "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(fname)}
    return None


def satellite(e, now):
    if e.get("lat") is None or e.get("lon") is None:
        return None
    day = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    la, lo = e["lat"], e["lon"]
    bbox = "%.2f,%.2f,%.2f,%.2f" % (max(-90, la - 4), max(-180, lo - 4), min(90, la + 4), min(180, lo + 4))
    return {"src": ("https://wvs.earthdata.nasa.gov/api/v1/snapshot?REQUEST=GetSnapshot&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor"
                    "&CRS=EPSG:4326&TIME=%s&WRAP=DAY&BBOX=%s&FORMAT=image/jpeg&WIDTH=480&HEIGHT=480" % (day, bbox)),
            "credit": "NASA EOSDIS Global Imagery Browse Services (GIBS) and Worldview, MODIS Terra true colour",
            "credit_url": "https://worldview.earthdata.nasa.gov/", "date": day,
            "note": "Satellite view of the wider area on %s. It may not show the event." % day}


def validate_item(c):
    """True when every shown part carries its required credit. Used by the data job and by tests."""
    s, im, sat = c.get("summary"), c.get("image"), c.get("satellite")
    if s and not (s.get("text") and s.get("title") and (s.get("url") or "").startswith("https://en.wikipedia.org/")
                  and s.get("licence") == "CC BY-SA 4.0" and (s.get("history_url") or "").startswith("https://en.wikipedia.org/")):
        return False
    if im and not (im.get("author") and licence_ok(im.get("license")) and (im.get("credit_url") or "").startswith("https://commons.wikimedia.org/")
                   and (im.get("src") or "").startswith("https://commons.wikimedia.org/") and not BAD_IMAGE.search(im["src"])):
        return False
    if sat and not (sat.get("credit") and "NASA" in sat["credit"] and (sat.get("src") or "").startswith("https://wvs.earthdata.nasa.gov/")
                    and sat.get("date")):
        return False
    return bool(s or im or sat)


def build_one(e, now, get=get_json, cache=None):
    cache = cache if cache is not None else {}
    ctx = {}
    for kind, title in titles_for(e):
        key = "wiki:" + title
        entry = cache.get(key)
        if entry and (now - datetime.fromisoformat(entry["t"])).days < CACHE_DAYS:
            data = entry["v"]
        else:
            try:
                summ = wiki_summary(title, get)
            except Exception:  # noqa: BLE001
                summ = None
            data = None
            if good_match(kind, summ):
                data = {"summary": {"text": summ["extract"], "title": summ["title"], "licence": "CC BY-SA 4.0",
                                    "url": (summ.get("content_urls") or {}).get("desktop", {}).get("page") or "https://en.wikipedia.org/wiki/" + urllib.parse.quote(summ["title"].replace(" ", "_")),
                                    "history_url": "https://en.wikipedia.org/w/index.php?title=%s&action=history" % urllib.parse.quote(summ["title"].replace(" ", "_"))}}
                try:
                    fn = page_image_name(summ["title"], get)
                    if fn and not BAD_IMAGE.search(fn):
                        img = commons_credit(fn, get)
                        if img:
                            data["image"] = img
                except Exception:  # noqa: BLE001
                    pass
            cache[key] = {"t": now.isoformat(), "v": data}
        if data:
            ctx.update(data)
            break
    sat = satellite(e, now)
    if sat:
        ctx["satellite"] = sat
    return ctx if ctx and validate_item(ctx) else None


def add_context(events, now, cache_path=None, get=get_json):
    cache = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
    n = 0
    for e in events[:MAX_EVENTS]:
        try:
            c = build_one(e, now, get, cache)
        except Exception:  # noqa: BLE001
            c = None
        if c:
            e["context"] = c
            n += 1
        time.sleep(0.2)
    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, separators=(",", ":"))
    return n


def validate_file(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    bad = [e["id"] for e in d["events"] if e.get("context") and not validate_item(e["context"])]
    if bad:
        print("invalid context on:", bad)
        return 1
    print("context ok on %d events" % sum(1 for e in d["events"] if e.get("context")))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(validate_file(sys.argv[1]))
