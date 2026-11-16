"""GD7 part A: our own probes of signed-out public pages of consumer services.

Plain code only. No model calls anywhere in this file. Standard library only.

Rules (specs/GD7-service-outage-probes.md):
- One GET per service per INTERVAL_S at most. Plain User-Agent that names the desk. Never credentials, cookies or form posts.
- A probe is "hard bad" for a 5xx or a timeout or a connection error.
- A probe is "soft bad" for a 2xx or 3xx page without the check word, or a response slower than SLOW_FACTOR times the 24-hour median.
- A 403 or 429 is "blocked": the service refuses plain probes. It counts as neither healthy nor bad.
- down      = DOWN_RUN probes in a row that are hard bad.
- degraded  = DOWN_RUN probes in a row that are bad (hard or soft), not all hard.
- healthy again = CLEAR_RUN healthy probes in a row.
- unprobeable = the first BASELINE_N probes were all blocked, or never reachable (timeout or error), and nothing healthy was ever seen.
  It stays out of outage detection until a healthy probe appears. This stops a service that blocks us from showing as a false outage.
"""
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "breakingnewsdesklive/1.0 (+https://breakingnewsdesklive.com/about.html; service status probe)"
INTERVAL_S = 180
TIMEOUT_S = 15
SLOW_FACTOR = 3
DOWN_RUN = 3
CLEAR_RUN = 3
BASELINE_N = 3
GROUP_WINDOW_S = 600
HISTORY_KEEP = 480          # 24 hours at one probe per 3 minutes
MEDIAN_MIN_SAMPLES = 20
INCIDENT_KEEP_S = 24 * 3600
STALE_AFTER_S = 30 * 60
ABOUT_URL = "https://breakingnewsdesklive.com/data.html#probes"

BLOCKED = (403, 429)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def http_fetch(url, timeout=TIMEOUT_S):
    """One GET. Returns (status, body_text, ms). Raises TimeoutError or OSError on a network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5"}, method="GET")
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400000).decode("utf-8", "ignore")
            return r.status, body, int((time.time() - t) * 1000)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(50000).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            body = ""
        return e.code, body, int((time.time() - t) * 1000)
    except TimeoutError:
        raise
    except urllib.error.URLError as e:
        if "timed out" in str(e.reason):
            raise TimeoutError(str(e.reason))
        raise OSError(str(e.reason))


def probe_once(svc, now, fetch=http_fetch):
    """Run one probe of one service. Returns a result dict. Never raises."""
    res = {"t": iso(now), "code": None, "ms": None, "word": False, "err": ""}
    try:
        code, body, ms = fetch(svc["login_url"], TIMEOUT_S)
        res.update(code=code, ms=ms, word=(svc["check_word"].lower() in (body or "").lower()))
    except TimeoutError:
        res["err"] = "timeout"
    except Exception as e:  # noqa: BLE001
        res["err"] = type(e).__name__
    return res


def classify(res, median_ms):
    """Return one of: healthy, hard, soft, blocked."""
    if res["err"] or res["code"] is None:
        return "hard"
    if res["code"] in BLOCKED:
        return "blocked"
    if res["code"] >= 500:
        return "hard"
    if res["code"] >= 400:
        return "soft"
    if not res["word"]:
        return "soft"
    if median_ms and res["ms"] is not None and res["ms"] > SLOW_FACTOR * median_ms:
        return "soft"
    return "healthy"


def median_ok_ms(history):
    xs = [h["ms"] for h in history if h.get("kind") == "healthy" and h.get("ms") is not None]
    return statistics.median(xs) if len(xs) >= MEDIAN_MIN_SAMPLES else None


def new_service_state():
    return {"history": [], "status": "up", "since": None, "ever_healthy": False}


def update(state, svc, res):
    """Add one probe result to the service state and move the status. Returns the new status."""
    st = state.setdefault("services", {}).setdefault(svc["id"], new_service_state())
    kind = classify(res, median_ok_ms(st["history"]))
    st["history"].append({"t": res["t"], "code": res["code"], "ms": res["ms"], "kind": kind})
    st["history"] = st["history"][-HISTORY_KEEP:]
    if kind == "healthy":
        st["ever_healthy"] = True
    h = st["history"]
    kinds = [x["kind"] for x in h]
    # Unprobeable: all of the first probes were blocked and nothing healthy was ever seen.
    # False-headline guard: a service that was never healthy cannot be told from one that refuses plain probes
    # (a WAF may answer our address with a challenge, a 404, a 5xx or a timeout). It can never be degraded or down.
    if not st["ever_healthy"]:
        if len(h) >= BASELINE_N:
            st["status"], st["since"] = "unprobeable", st["since"] or res["t"]
        return st["status"]
    last = kinds[-DOWN_RUN:]
    prev = st["status"]
    if prev == "unprobeable" and kind != "healthy":
        return prev
    if len(last) == DOWN_RUN and all(k == "hard" for k in last):
        new = "down"
    elif len(last) == DOWN_RUN and all(k in ("hard", "soft") for k in last):
        new = "degraded" if prev != "down" else "down"
    elif len(kinds) >= CLEAR_RUN and all(k == "healthy" for k in kinds[-CLEAR_RUN:]):
        new = "up"
    else:
        new = prev if prev != "unprobeable" else ("up" if kind == "healthy" else prev)
    if new in ("down", "degraded") and prev not in ("down", "degraded"):
        # First failing probe of this run is when the trouble began.
        n = 0
        for k in reversed(kinds):
            if k in ("hard", "soft"):
                n += 1
            else:
                break
        st["since"] = h[-n]["t"]
    if new == "up" and prev in ("down", "degraded"):
        state.setdefault("incidents", []).append({"service": svc["id"], "start": st["since"], "end": res["t"], "worst": prev})
        st["since"] = None
    if new == "unprobeable":
        st["since"] = st["since"] or res["t"]
    st["status"] = new
    return new


def run_cycle(state, services, now, fetch=http_fetch, last_probe=None):
    """Probe every service once, respecting INTERVAL_S per service. `last_probe` maps id -> datetime of the last GET.
    Returns the list of (service id, result) probed. A service probed less than INTERVAL_S ago is skipped."""
    last_probe = last_probe if last_probe is not None else {}
    done = []
    for svc in services:
        lp = last_probe.get(svc["id"])
        if lp and (now - lp).total_seconds() < INTERVAL_S:
            continue
        res = probe_once(svc, now, fetch)
        last_probe[svc["id"]] = now
        update(state, svc, res)
        done.append((svc["id"], res))
    prune(state, now)
    return done


def prune(state, now):
    cut = now - timedelta(seconds=INCIDENT_KEEP_S)
    state["incidents"] = [i for i in state.get("incidents", []) if parse(i["end"]) >= cut]


def et_clock(dt):
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York")).strftime("%-I:%M %p ET").replace("AM", "AM").replace("PM", "PM")
    except Exception:  # noqa: BLE001
        return dt.strftime("%H:%M UTC")


def group_words(group):
    return {"bank": "bank", "payment app": "payment app", "card issuer": "card issuer", "carrier": "carrier", "airline": "airline"}.get(group, "service")


def snapshot(state, services, now):
    """The public file data/probes.json: current status for each service, plus 24-hour incidents."""
    by_id = {s["id"]: s for s in services}
    out = []
    for sid, st in state.get("services", {}).items():
        svc = by_id.get(sid)
        if not svc:
            continue
        last = st["history"][-1] if st["history"] else {}
        out.append({"id": sid, "name": svc["name"], "group": svc["group"], "status": st["status"], "since": st["since"],
                    "last_probe": last.get("t"), "last_code": last.get("code"), "last_ms": last.get("ms"), "ever_healthy": bool(st.get("ever_healthy"))})
    return {"generated": iso(now), "interval_s": INTERVAL_S, "services": out, "incidents": state.get("incidents", [])}


def _plural_groups(members):
    groups = {s["group"] for s in members}
    if len(groups) == 1:
        g = group_words(next(iter(groups)))
        return "%d %s login pages" % (len(members), g)
    return "%d service login pages" % len(members)


def events_from_snapshot(snap, now):
    """Build site events (type outage) from a probes.json snapshot. Group services whose trouble began within GROUP_WINDOW_S."""
    if not snap or "generated" not in snap:
        return []
    if (now - parse(snap["generated"])).total_seconds() > STALE_AFTER_S:
        return []
    bad = [s for s in snap["services"] if s["status"] in ("down", "degraded") and s["since"]]
    bad.sort(key=lambda s: s["since"])
    groups = []
    for s in bad:
        t = parse(s["since"])
        if groups and (t - parse(groups[-1][0]["since"])).total_seconds() <= GROUP_WINDOW_S:
            groups[-1].append(s)
        else:
            groups.append([s])
    events = []
    for g in groups:
        first = parse(g[0]["since"])
        n = len(g)
        names = ", ".join(s["name"] for s in g)
        worst = "down" if any(s["status"] == "down" for s in g) else "degraded"
        what = "returning errors" if worst == "down" else "responding badly"
        title = ("%s login page %s" % (g[0]["name"], what)) if n == 1 else ("%s %s" % (_plural_groups(g), what))
        summary = "The desk probes measured %s on the signed-out page of: %s. First failing probe at %s. This is what the desk measured, not a statement by the service." % (
            "errors or no response" if worst == "down" else "failed checks or slow responses", names, et_clock(first))
        events.append({
            "id": "probe-%s" % first.strftime("%Y%m%d%H%M"), "type": "outage", "title": title, "place": "United States",
            "lat": None, "lon": None, "time": iso(first), "severity": "severe" if n >= 3 else "moderate", "size": n,
            "source": "Desk probes (our own)", "source_id": "probes", "source_url": ABOUT_URL,
            "detail": {"lane": "probes", "open": True, "services": [{"id": s["id"], "name": s["name"], "status": s["status"], "since": s["since"]} for s in g],
                       "measured_at": et_clock(first), "services_failing": n},
            "region": "Americas", "big": n >= 3 and all(s.get("ever_healthy") for s in g), "summary_override": summary,
        })
    # Cleared items stay in the 24-hour history as quiet items.
    by_id = {s["id"]: s for s in snap["services"]}
    for inc in snap.get("incidents", []):
        svc = by_id.get(inc["service"])
        if not svc:
            continue
        end = parse(inc["end"])
        events.append({
            "id": "probe-clear-%s-%s" % (inc["service"], end.strftime("%Y%m%d%H%M")), "type": "outage",
            "title": "%s login page: errors cleared" % svc["name"], "place": "United States", "lat": None, "lon": None,
            "time": iso(end), "severity": "minor", "size": 1, "source": "Desk probes (our own)", "source_id": "probes", "source_url": ABOUT_URL,
            "detail": {"lane": "probes", "open": False, "service": svc["id"], "trouble_began": inc["start"], "cleared": inc["end"], "began_at": et_clock(parse(inc["start"])), "cleared_at": et_clock(end)},
            "region": "Americas", "big": False,
            "summary_override": "The desk probes measured three healthy responses in a row at %s after trouble that began at %s." % (et_clock(end), et_clock(parse(inc["start"]))),
        })
    return events


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default
