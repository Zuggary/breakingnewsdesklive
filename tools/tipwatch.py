"""GD8 part 7: the TIP watcher. INTERNAL ONLY. Its output is never published and never shown on the site.

Reads the public RSS and Atom feeds of big outlets (headline, link and time only), keeps them for at most 48 hours,
groups headlines that several outlets carry, and writes leads: "N outlets report X". A lead is a tip to go and source the facts
from primary sources. A lead is not evidence and its wording is never copied onto the site.

Rules
- Feeds only. No page scraping. robots.txt is read first: a 404 means no limits, any other failure means skip the feed this round.
- One request per feed per round. Rounds are 2 to 5 minutes apart. A feed that sends 304 Not Modified costs almost nothing.
- Clustering and tagging are plain code. An optional local model (Apple `apfel`) tags headlines the rules cannot place. No cloud model.
- The store and the leads live outside the repository (default ~/factory-scratch/tipwatch). A path inside the repo is refused.
Usage: python tools/tipwatch.py --once            one round
       python tools/tipwatch.py --loop 3600 --every 180   rounds every 180 s for 3600 s  (a persistent job: tell the CoS first)
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import auto_news  # noqa: E402

UA = "breakingnewsdesklive-tips/1.0 (+https://breakingnewsdesklive.com/about; internal headline reader)"
KEEP_HOURS = 48
CLUSTER_WINDOW_H = 6
MIN_OUTLETS = 2
TIMEOUT_S = 20
ROBOTS_TTL_S = 24 * 3600
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DIR = os.path.expanduser("~/factory-scratch/tipwatch")

FEEDS = [
    {"id": "aljazeera", "name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"id": "cnn", "name": "CNN", "url": "http://rss.cnn.com/rss/cnn_topstories.rss"},
    {"id": "bbc", "name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml"},
    {"id": "npr", "name": "NPR", "url": "https://feeds.npr.org/1001/rss.xml"},
    {"id": "guardian", "name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
    {"id": "cbs", "name": "CBS News", "url": "https://www.cbsnews.com/latest/rss/main"},
    {"id": "nbc", "name": "NBC News", "url": "https://feeds.nbcnews.com/nbcnews/public/news"},
    # AP: no public feed (HTTP 403 on the feed URL tried). Left out.
]

STOP = set("""about after again also amid back been before being between could does down during from have here into just last more most
new news over says said than that their them then there these they this those through today under until very what when where which while
will with would your live update updates video watch breaking report reports reported""".split())

SECURITY_RX = re.compile(r"\b(dirty bomb|chemical attack|radiological|explosion|explosions|blast|bomb threat|bombing|evacuat\w+|shooting|gunman|cyberattack|cyber attack|ransomware|hostage|hostages|terror\w*|attack on|plot against|threat(?:s)? (?:to|against)|ground stop|lockdown|shelter in place|state of emergency|missile|airstrike|drone attack|attacks?|threats?|shelter\w*|plot(?:s|ting|ted)?)\b", re.I)
RESPONSE_RX = re.compile(r"\b(white house|pentagon|state department|fbi|dhs|homeland security|cia|nsa|secret service|spokesperson|spokesman|officials? say|denies|denied|no credible|statement)\b", re.I)

TOPICS = [
    ("aviation", r"\b(airline|airlines|flight|flights|airport|airports|faa|plane|planes|pilot|aircraft|departures|ground stop|united airlines|delta|southwest|american airlines|boeing|airbus)\b"),
    ("finance", r"\b(bank|banks|banking|jpmorgan|chase|wells fargo|bank of america|stocks|markets|fed|inflation|dollar|zelle|venmo|paypal|sec filing)\b"),
    ("outage", r"\b(outage|outages|down for|not working|glitch|cyberattack|cyber attack|hack|hacked|ransomware|data breach)\b"),
    ("weather", r"\b(storm|hurricane|tornado|flood|floods|flooding|blizzard|wildfire|earthquake|tsunami|typhoon|heatwave|snow)\b"),
    ("conflict", r"\b(war|attack|attacks|strike|strikes|missile|troops|ceasefire|killed|shooting|bomb|bombing|hostage|hostages|invasion)\b"),
    ("politics", r"\b(president|election|congress|senate|parliament|minister|trump|biden|vote|court|supreme court|tariff|sanctions)\b"),
    ("health", r"\b(outbreak|virus|vaccine|hospital|disease|health|measles|cdc|who)\b"),
]
_TOPIC_RX = [(t, re.compile(p, re.I)) for t, p in TOPICS]
_AVIATION_RX = dict(_TOPIC_RX)["aviation"]


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def refuse_published_path(path):
    """The store and the leads must never sit inside the repository, where a build could publish them."""
    real = os.path.realpath(path)
    if real == REPO_ROOT or real.startswith(REPO_ROOT + os.sep):
        raise ValueError("tip files must live outside the repository: %s" % path)
    return path


# ---------- feeds ----------

def parse_feed(xml_text, feed_id):
    """Return [{feed, title, link, time}] from RSS 2.0 or Atom. Headline, link and time only."""
    root = ET.fromstring(xml_text)
    out = []
    items = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for it in items:
        def tx(*names):
            for n in names:
                el = it.find(n)
                if el is not None and (el.text or "").strip():
                    return el.text.strip()
            return ""
        title = tx("title", "{http://www.w3.org/2005/Atom}title")
        link = tx("link")
        if not link:
            a = it.find("{http://www.w3.org/2005/Atom}link")
            link = a.get("href", "") if a is not None else ""
        when = tx("pubDate", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published")
        try:
            dt = parsedate_to_datetime(when) if "," in when or when[:3].isalpha() else datetime.fromisoformat(when.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if title and link.startswith("http"):
            out.append({"feed": feed_id, "title": " ".join(title.split())[:200], "link": link, "time": iso(dt)})
    return out


def robots_allows(url, fetch, cache, now):
    """Respect robots.txt. 404 = no limits. Any other failure = skip this feed this round."""
    m = re.match(r"(https?://[^/]+)", url)
    host = m.group(1)
    hit = cache.get(host)
    if hit and (now - parse_iso(hit["t"])).total_seconds() < ROBOTS_TTL_S:
        return hit["ok"]
    code, body = fetch(host + "/robots.txt")
    if code == 404:
        ok = True
    elif code == 200:
        ok = _robots_ok(body or "", url[len(host):] or "/")
    else:
        return False
    cache[host] = {"t": iso(now), "ok": ok}
    return ok


def _robots_ok(text, path):
    """Minimal robots.txt reader: rules for '*' only; the longest matching rule wins; Allow wins a tie."""
    star, rules = False, []
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        if k.lower() == "user-agent":
            star = (v == "*")
        elif star and k.lower() in ("allow", "disallow") and v:
            rules.append((k.lower(), v))
    best = (-1, True)
    for kind, pat in rules:
        if path.startswith(pat.rstrip("*")) and len(pat) > best[0]:
            best = (len(pat), kind == "allow")
        elif path.startswith(pat.rstrip("*")) and len(pat) == best[0] and kind == "allow":
            best = (len(pat), True)
    return best[1]


def http_fetch(url, headers=None):
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, r.read(600000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return 0, ""



# ---------- GDELT as a tip source (security stories only) ----------
# CNN's public RSS has been stale since 2023, so a CNN scoop reaches us only when other outlets carry it. GDELT lists page titles
# from thousands of outlets every 15 minutes. We keep titles that match the security words and nothing else. Internal only.

def read_gkg_security(zip_bytes):
    """Return [{feed (domain), title, link, time}] for titles that match SECURITY_RX. Headline, link and time only."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    out = []
    for line in z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines():
        f = line.split("\t")
        if len(f) < 27 or f[25] or not f[4].startswith("http"):
            continue
        m = re.search(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", f[26], re.S)
        if not m:
            continue
        title = " ".join(m.group(1).split())
        if SECURITY_RX.search(title):
            out.append({"feed": f[3].lower().replace("www.", ""), "title": title[:200], "link": f[4],
                        "time": f[1][:4] + "-" + f[1][4:6] + "-" + f[1][6:8] + "T" + f[1][8:10] + ":" + f[1][10:12] + ":" + f[1][12:14] + "Z"})
    return out


def gdelt_security_items(store, fetch_bytes, now):
    """Read the newest GKG file once. fetch_bytes(url) -> bytes or None."""
    txt = fetch_bytes("https://data.gdeltproject.org/gdeltv2/lastupdate.txt")
    if not txt:
        return []
    m = re.search(r"/gdeltv2/(\d{14})\.gkg\.csv\.zip", txt.decode("utf-8", "replace"))
    if not m or store.get("gdelt_last") == m.group(1):
        return []
    z = fetch_bytes("https://data.gdeltproject.org/gdeltv2/%s.gkg.csv.zip" % m.group(1))
    if not z:
        return []
    store["gdelt_last"] = m.group(1)
    return read_gkg_security(z)


def http_bytes(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
            return r.read()
    except Exception:  # noqa: BLE001
        return None


# ---------- store ----------

def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"items": [], "robots": {}}


def add_items(store, items, now):
    """Add new items (dedupe on link). Drop everything older than KEEP_HOURS."""
    known = {i["link"] for i in store["items"]}
    for it in items:
        if it["link"] not in known:
            store["items"].append(dict(it, seen=iso(now)))
            known.add(it["link"])
    cut = now - timedelta(hours=KEEP_HOURS)
    store["items"] = [i for i in store["items"] if parse_iso(i["time"]) >= cut]
    return store


# ---------- clustering and tagging ----------

def tokens(title):
    t = re.sub(r"\s[-|–—]\s[^-|–—]{2,40}$", "", title)        # drop a trailing outlet name
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’]+", t)
    out = set()
    for w in words:
        lw = w.lower().strip("'’")
        if lw in STOP or len(lw) < 4 and not w.isupper() and not w.isdigit():
            continue
        out.add(lw)
    return out


def similar(a, b):
    if not a or not b:
        return False
    inter = len(a & b)
    return inter >= 3 and inter / float(len(a | b)) >= 0.3 or inter >= 2 and inter / float(min(len(a), len(b))) >= 0.6


def tag_topic(title, local_model=None):
    if SECURITY_RX.search(title):
        return "security"
    for topic, rx in _TOPIC_RX:
        if rx.search(title):
            return topic
    if local_model:
        t = local_model(title)
        if t:
            return t
    return "other"


def apfel_sentence(titles, timeout=40):
    """Optional: one neutral factual sentence from the on-device model, built only from the headlines. None on any failure."""
    try:
        prompt = ("Write ONE neutral factual sentence of at most 25 words that says what is reported. Use only facts in these headlines. "
                  "No adjectives, no opinion, no new names or numbers. Headlines: " + " | ".join(t[:140] for t in titles[:4]))
        out = subprocess.run(["apfel", prompt], capture_output=True, text=True, timeout=timeout, check=True).stdout.strip().split("\n")[0]
        return out if 3 <= len(out.split()) <= 40 else None
    except Exception:  # noqa: BLE001
        return None


def apfel_tag(title, timeout=20):
    """Optional: ask the on-device model for one word. Returns None when apfel is missing or fails."""
    try:
        out = subprocess.run(["apfel", "Reply with one word from: aviation, finance, outage, weather, conflict, politics, health, sports, other. Headline: " + title[:200]],
                             capture_output=True, text=True, timeout=timeout, check=True).stdout.strip().lower()
        w = re.findall(r"[a-z]+", out)
        return w[0] if w and w[0] in {t for t, _ in TOPICS} | {"sports", "other"} else None
    except Exception:  # noqa: BLE001
        return None


def build_leads(store, now, local_model=None):
    items = sorted(store["items"], key=lambda i: i["time"])
    clusters = []
    for it in items:
        tk = tokens(it["title"])
        t = parse_iso(it["time"])
        for c in clusters:
            if (t - parse_iso(c["last"])).total_seconds() <= CLUSTER_WINDOW_H * 3600 and similar(tk, c["tk"]):
                c["items"].append(it)
                c["tk"] |= tk
                c["last"] = it["time"]
                break
        else:
            clusters.append({"tk": set(tk), "items": [it], "first": it["time"], "last": it["time"]})
    leads = []
    for c in clusters:
        feeds = sorted({i["feed"] for i in c["items"]})
        if len(feeds) < MIN_OUTLETS:
            continue
        head = sorted(c["items"], key=lambda i: i["time"])[0]
        leads.append({
            "id": "lead-%s-%s" % (parse_iso(c["first"]).strftime("%Y%m%d%H%M"), feeds[0]),
            "topic": tag_topic(head["title"], local_model), "outlets": feeds, "n_outlets": len(feeds),
            "first_seen": c["first"], "last_seen": c["last"],
            "keywords": sorted(c["tk"])[:12],
            "items": [{"feed": i["feed"], "title": i["title"], "link": i["link"], "time": i["time"]} for i in sorted(c["items"], key=lambda i: i["time"])[:8]],
            "next": "Source the facts from primary sources, write our own wording, link the primary source. Air only when Corroborated.",
        })
    leads.sort(key=lambda l: (-l["n_outlets"], l["first_seen"]))
    return leads


def security_candidates(leads):
    """Major security and national-news candidates: 2 or more outlets on a security story. INTERNAL.
    A candidate never publishes itself. It lists what a person must add before an item can show:
    an official response line, a primary-source link, and calm wording. Headlines that carry a response are shown as hints only."""
    out = []
    for l in leads:
        if l["topic"] != "security":
            continue
        hints = [i["title"] for i in l["items"] if RESPONSE_RX.search(i["title"])][:3]
        titles = {re.sub(r"\W+", " ", i["title"].lower()).strip() for i in l["items"]}
        out.append({"lead": l["id"], "distinct_headlines": len(titles), "n_outlets": l["n_outlets"], "outlets": l["outlets"], "first_seen": l["first_seen"], "items": l["items"][:6],
                    "response_hints": hints, "official_response_found": bool(hints),
                    "needs": ["official response line (from the agency or office, read directly)", "primary-source link", "calm wording, DC not Washington State, no alarm words"],
                    "publish": "Only through manual_items.json after a person adds the needs. Never automatic."})
    return out


def alerts_for(candidates, seen):
    """Lines for ALERTS.md: a security candidate carried by 5 or more outlets with 2 or more distinct headlines, not yet noted.
    Nobody publishes from this. It tells a person to look now."""
    out = []
    for c in candidates:
        if c["n_outlets"] >= 5 and c["distinct_headlines"] >= 2 and c["lead"] not in seen:
            seen.add(c["lead"])
            out.append("- %s | %d outlets | %d headlines | response found: %s | %s" % (c["first_seen"], c["n_outlets"], c["distinct_headlines"], c["official_response_found"], c["items"][0]["title"][:110]))
    return out


# ---------- one round ----------

def run_round(store, feeds, now, fetch=http_fetch, local_model=None, gdelt_bytes=None):
    status = []
    for f in feeds:
        rec = {"id": f["id"], "ok": False, "new": 0}
        try:
            if not robots_allows(f["url"], fetch, store.setdefault("robots", {}), now):
                rec["error"] = "robots or robots unreachable"
                status.append(rec)
                continue
            code, body = fetch(f["url"])
            if code != 200:
                rec["error"] = "HTTP %s" % code
                status.append(rec)
                continue
            before = len(store["items"])
            add_items(store, parse_feed(body, f["id"]), now)
            rec["ok"], rec["new"] = True, len(store["items"]) - before
        except Exception as e:  # noqa: BLE001
            rec["error"] = type(e).__name__
        status.append(rec)
    if gdelt_bytes:
        rec = {"id": "gdelt-security", "ok": False, "new": 0}
        try:
            before = len(store["items"])
            add_items(store, gdelt_security_items(store, gdelt_bytes, now), now)
            rec["ok"], rec["new"] = True, len(store["items"]) - before
        except Exception as e:  # noqa: BLE001
            rec["error"] = type(e).__name__
        status.append(rec)
    add_items(store, [], now)
    return build_leads(store, now, local_model), status


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0)
    ap.add_argument("--every", type=int, default=180)
    ap.add_argument("--no-gdelt", action="store_true", help="skip the GDELT security titles")
    ap.add_argument("--apfel", action="store_true", help="tag headlines the rules cannot place with the on-device model")
    a = ap.parse_args(argv)
    refuse_published_path(a.dir)
    os.makedirs(a.dir, exist_ok=True)
    store_path, leads_path, av_path, sec_path = (os.path.join(a.dir, n) for n in ("store.json", "leads.json", "aviation-leads.json", "security-candidates.json"))
    end = time.time() + a.loop
    while True:
        now = now_utc()
        store = load(store_path)
        leads, status = run_round(store, FEEDS, now, local_model=apfel_tag if a.apfel else None, gdelt_bytes=None if a.no_gdelt else http_bytes)
        for path, obj in ((store_path, store), (leads_path, {"generated": iso(now), "note": "INTERNAL. Never publish.", "leads": leads, "feeds": status}),
                          (av_path, {"generated": iso(now), "note": "INTERNAL. For Lane 5 (Air Travel Desk). Never publish.", "leads": [l for l in leads if l["topic"] == "aviation" or (l["topic"] == "security" and _AVIATION_RX.search(l["items"][0]["title"]))]}),
                          (sec_path, {"generated": iso(now), "note": "INTERNAL. Candidates for a curated Reported item. Never publish.", "candidates": security_candidates(leads)}),
                          (os.path.join(a.dir, "proposed-items.json"), {"generated": iso(now), "note": "INTERNAL. Proposed curated items. A ready one still goes live only through manual_items.json and the guarded push.",
                                                                           "proposals": [auto_news.propose(c, now, apfel_sentence if a.apfel else None) for c in security_candidates(leads)]})):
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=1)
            os.replace(path + ".tmp", path)
        seen = set(store.setdefault("alerted", []))
        lines = alerts_for(security_candidates(leads), seen)
        if lines:
            with open(os.path.join(a.dir, "ALERTS.md"), "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            store["alerted"] = sorted(seen)
            with open(store_path, "w", encoding="utf-8") as f:
                json.dump(store, f, indent=1)
        print("%s feeds_ok=%d items=%d leads=%d aviation=%d" % (iso(now), sum(s["ok"] for s in status), len(store["items"]), len(leads), sum(1 for l in leads if l["topic"] == "aviation")), flush=True)
        if a.once or time.time() >= end:
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
