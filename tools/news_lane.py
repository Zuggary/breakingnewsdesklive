"""GD7 part B: the "News reports" lane. Headline and link only. Plain code, no model calls.

Input: article records {title, domain, url, seendate} from a news feed whose terms allow headline display (GDELT, see research/GD7-sources.md).
A headline counts when it holds an outage word and the name of a service from tools/probe_list.json.
A service qualifies when 2 or more different outlets report it within WINDOW_S.
Services of the same kind that qualify within the same window become one item. An item with 3 or more outlets is "big" and takes the top headline slot.
The item shows the outlet's headline as a link. It never holds article text.
"""
import re
from datetime import datetime, timedelta, timezone

LABEL = "News reports, not confirmed by the desk"
WINDOW_S = 3600
MIN_OUTLETS = 2
BIG_OUTLETS = 3
MAX_LINKS = 6
ABOUT_URL = "https://breakingnewsdesklive.com/about#news-reports"

OUTAGE_RE = re.compile(
    r"\b(outages?|(?:is|are|went|goes|was|were)\s+down|down\s+for|not\s+working|reporting\s+problems|report(?:ed|s)?\s+problems|"
    r"glitch(?:es)?|can(?:'|’)?t\s+log\s*in|cannot\s+log\s*in|unable\s+to\s+log\s*in|log-?in\s+(?:issues|problems|troubles?|errors?|failures?)|"
    r"technical\s+(?:issues?|glitch(?:es)?|problems?|bug)|service\s+disruptions?|disrupt(?:ed|ion)s?|down\s+for\s+(?:many|some|users|customers))\b", re.I)

RESOLVED_RE = re.compile(r"\b(?:resum(?:e|ed|es|ing)|fixed|resolved|restored|back\s+to\s+normal|lifted|issue\s+(?:is\s+)?over)\b", re.I)

# Names that are also common words need a second word, so "chase" the verb and "united" the adjective do not match.
ALIASES = {
    "chase": [r"JPMorgan Chase", r"Chase Bank", r"Chase (?:customers|app|online|mobile|login|log-in|accounts?)", r"Chase\b(?=.*\b(?:bank|banking)\b)"],
    "bofa": [r"Bank of America", r"BofA"],
    "wellsfargo": [r"Wells Fargo"],
    "citi": [r"Citibank", r"Citi Bank", r"Citi (?:customers|app|online)"],
    "usbank": [r"U\.S\. Bank", r"US Bank"],
    "pnc": [r"PNC\b"],
    "truist": [r"Truist"],
    "capitalone": [r"Capital One"],
    "tdbank": [r"TD Bank"],
    "regions": [r"Regions Bank"],
    "navyfederal": [r"Navy Federal"],
    "ally": [r"Ally Bank", r"Ally Financial"],
    "zelle": [r"Zelle"],
    "venmo": [r"Venmo"],
    "paypal": [r"PayPal"],
    "cashapp": [r"Cash App"],
    "amex": [r"American Express", r"\bAmex\b"],
    "discover": [r"Discover (?:card|Financial|Bank|customers)"],
    "synchrony": [r"Synchrony"],
    "barclays": [r"Barclays US", r"Barclaycard US"],
    "bread": [r"Bread Financial"],
    "creditone": [r"Credit One"],
    "verizon": [r"Verizon"],
    "att": [r"AT&T"],
    "tmobile": [r"T-Mobile"],
    "cricket": [r"Cricket Wireless"],
    "american": [r"American Airlines"],
    "delta": [r"Delta Air Lines", r"Delta Airlines", r"Delta (?:flights|passengers|customers|outage)"],
    "united": [r"United Airlines", r"United (?:flights|departures|planes|says|said|reports|confirms)\b"],
    "southwest": [r"Southwest Airlines"],
}
_COMPILED = {sid: [re.compile(p) for p in pats] for sid, pats in ALIASES.items()}
# A bare common-word name counts only when the same headline already names another service from the list.
BARE = {"chase": re.compile(r"\bChase\b"), "citi": re.compile(r"\bCiti\b"), "delta": re.compile(r"\bDelta\b"), "united": re.compile(r"\bUnited\b"),
        "american": re.compile(r"\bAmerican\b"), "ally": re.compile(r"\bAlly\b")}


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def seen_time(a):
    s = a["seendate"]
    return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) if "-" not in s else parse(s)


def match(title):
    """Return the list of probe-list service ids named in a headline that also holds an outage word. Empty when none."""
    if not title or not (OUTAGE_RE.search(title) or RESOLVED_RE.search(title)):
        return []
    found = [sid for sid, pats in _COMPILED.items() if any(p.search(title) for p in pats)]
    if found:
        found += [sid for sid, rx in BARE.items() if sid not in found and rx.search(title)]
    return found


def collect(articles):
    """Keep only matching articles, with their service ids. Used while the feed is read, so nothing else is stored."""
    out = []
    for a in articles:
        sids = match(a.get("title", ""))
        if sids and (a.get("url") or "").startswith("https://"):
            t = a.get("title", "")
            out.append(dict(a, services=sids, outage=bool(OUTAGE_RE.search(t)), resolved=bool(RESOLVED_RE.search(t))))
    return out


def et_clock(dt):
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York")).strftime("%-I:%M %p ET")
    except Exception:  # noqa: BLE001
        return dt.strftime("%H:%M UTC")


def build_items(matched, services, now, probe_snapshot=None, window_s=WINDOW_S):
    """matched: output of collect(). services: probe list. Returns event dicts of type outage with detail.lane == "news"."""
    by_id = {s["id"]: s for s in services}
    per_service, resolved_by = {}, {}
    for a in matched:
        for sid in a["services"]:
            if sid in by_id:
                if a.get("outage", True):
                    per_service.setdefault(sid, []).append(a)
                if a.get("resolved"):
                    resolved_by.setdefault(sid, []).append(a)
    qualified = []
    for sid, arts in per_service.items():
        arts = sorted(arts, key=seen_time)
        # Best window: the first report and every report within window_s after it, from different outlets.
        best = []
        for i, a0 in enumerate(arts):
            win = [b for b in arts[i:] if (seen_time(b) - seen_time(a0)).total_seconds() <= window_s]
            outlets = {b["domain"] for b in win}
            if len(outlets) > len({b["domain"] for b in best}):
                best = win
        outlets = {b["domain"] for b in best}
        if len(outlets) >= MIN_OUTLETS:
            qualified.append({"sid": sid, "arts": best, "first": seen_time(best[0]), "outlets": outlets})
    qualified.sort(key=lambda q: q["first"])
    # Services of one kind (banks, airlines, carriers ...) that qualify within the same window make one item.
    # A bank story and an airline story are never merged: they have different readers and different links.
    groups = []
    for q in qualified:
        kind = by_id[q["sid"]]["group"]
        for g in groups:
            if by_id[g[0]["sid"]]["group"] == kind and (q["first"] - g[0]["first"]).total_seconds() <= window_s:
                g.append(q)
                break
        else:
            groups.append([q])
    probe_by_id = {s["id"]: s for s in (probe_snapshot or {}).get("services", [])}
    items = []
    for g in groups:
        first = min(q["first"] for q in g)
        arts, seen_urls = [], set()
        for q in g:
            for a in q["arts"]:
                if a["url"] not in seen_urls:
                    seen_urls.add(a["url"])
                    arts.append(a)
        arts.sort(key=seen_time)
        outlets = {a["domain"] for a in arts}
        names = [by_id[q["sid"]]["name"] for q in g]
        groups_in = {by_id[q["sid"]]["group"] for q in g}
        n = len(g)
        if n == 1:
            title = "News reports: %s problems reported by %d outlets" % (names[0], len(outlets))
        else:
            word = {"bank": "banks", "payment app": "payment apps", "card issuer": "card issuers", "carrier": "carriers", "airline": "airlines"}.get(next(iter(groups_in)), "services") if len(groups_in) == 1 else "services"
            title = "News reports: problems reported at %d %s, %d outlets" % (n, word, len(outlets))
        # Resolution reports: outlets, later than the first report, whose headline says fixed, resumed or restored.
        res_outlets = {}
        for q in g:
            for a in resolved_by.get(q["sid"], []):
                if seen_time(a) > first:
                    res_outlets.setdefault(a["domain"], a)
        probes_attached = []
        for q in g:
            p = probe_by_id.get(q["sid"])
            if p and p["status"] in ("down", "degraded") and p.get("since"):
                probes_attached.append({"service": p["name"], "status": p["status"], "since": p["since"], "measured_at": et_clock(parse(p["since"]))})
        summary = "%d outlets reported problems with %s between %s and %s. Headlines are the outlets' own words, linked below. %s." % (
            len(outlets), ", ".join(names), et_clock(first), et_clock(seen_time(arts[-1])), LABEL)
        resolution = None
        if len(res_outlets) >= MIN_OUTLETS:
            rt = max(seen_time(a) for a in res_outlets.values())
            resolution = {"outlets": len(res_outlets), "latest": et_clock(rt)}
            summary += " %d outlets report the problem fixed or operations resuming, latest %s. This is a report, not confirmed by the desk." % (len(res_outlets), et_clock(rt))
        if probes_attached:
            summary += " The desk probe measured: " + "; ".join("%s %s since %s" % (p["service"], p["status"], p["measured_at"]) for p in probes_attached) + "."
        big = len(outlets) >= BIG_OUTLETS
        items.append({
            "id": "news-%s-%s" % (first.strftime("%Y%m%d%H%M"), g[0]["sid"]), "type": "outage", "title": title, "place": "United States",
            "time": iso(first), "severity": "severe" if big else "moderate", "size": len(outlets),
            "source": "News reports (via GDELT)", "source_id": "news-lane", "source_url": ABOUT_URL,
            "detail": {"lane": "news", "label": LABEL, "open": True, "outlets": len(outlets), "services": names,
                       "first_report": et_clock(first), "last_report": et_clock(seen_time(arts[-1])), "probes": probes_attached, "resolution": resolution},
            "links": [{"label": a["domain"], "title": " ".join(a["title"].split())[:140], "url": a["url"]} for a in arts[:MAX_LINKS]],
            "region": "Americas", "big": big, "summary_override": summary,
        })
    return items
