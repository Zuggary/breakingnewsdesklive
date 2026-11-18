"""Keep a rolling record of FAA airport closures that may be routine."""
import json
import re
from datetime import timedelta, timezone
from pathlib import Path

from tools.lib import parse_time
from tools.probes import load_json

KNOWN_RECURRING = {"SNA"}
CLOSURE = re.compile(r"^Airport closed at ([A-Z0-9]{3,4})\b")
UNUSUAL = re.compile(
    r"\b(?:weather|wx|thunderstorms?|snow|fog|ice|icing|wind|accidents?|runways?|security|"
    r"hurricane|storm|tornado|flood|earthquake|smoke|ash|power|outage|strike|emergency|incident|crash|fire|evacuat|threat|medical|bird|unscheduled|unplanned|multi[-\s]?day|(?:\d+|two|three|several|multiple)\s*[- ]?\s*days)\b", re.I)


def filter_closures(events, now, out_dir=None):
    """Return visible events and, when building files, record sightings and exclusions."""
    today = now.astimezone(timezone.utc).date()
    window = {(today - timedelta(days=i)).isoformat() for i in range(7)}
    path = Path(out_dir) / "closure-days.json" if out_dir is not None else None
    history = load_json(path, {}) if path else {}
    if not isinstance(history, dict):
        history = {}
    days = {code: {day for day in dates if isinstance(day, str) and day in window}
            for code, dates in history.items() if isinstance(dates, list)}
    visible, dropped = [], []
    for event in events:
        match = CLOSURE.match(event["title"]) if event.get("source_id") == "atd-faa" else None
        # The FAA snapshot time is the poll time, so an end date alone gives no closure duration.
        if not match or event.get("severity") == "extreme" or UNUSUAL.search(event["title"] + " " + str(event.get("detail") or "")):
            visible.append(event)
            continue
        code = match[1]
        day = parse_time(event["time"]).date().isoformat()
        sightings = days.setdefault(code, set())
        if day in window:
            sightings.add(day)
        if code in KNOWN_RECURRING:
            reason = "Known recurring airport closure"
        elif len(sightings) >= 3:
            reason = "Airport closure seen on at least three of the last seven UTC days"
        else:
            visible.append(event)
            continue
        dropped.append({"id": event["id"], "reason": reason})
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({code: sorted(dates) for code, dates in days.items() if dates},
                                   sort_keys=True) + "\n", encoding="utf-8")
        path.with_name("routine.json").write_text(json.dumps(dropped, indent=1) + "\n", encoding="utf-8")
    return visible, dropped
