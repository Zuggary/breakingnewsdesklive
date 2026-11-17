"""Crisis kill switch (GD6 phase 1).

Two layers:
1. Item hold. An event whose title or place matches a crisis trigger (mass casualty, crash, shooting, attack, conflict words)
   is taken out of events.json and written to held.json with the reason. A person clears it by adding its id to approved.json.
2. Global stop. If the file KILL exists in the repo root, or BND_KILL=1, the data job publishes nothing new and keeps the last good files.
The job prints one HELD line for each item and one KILL line, so the Actions log and the CoS can see them.
"""
import json
import os
import re

TRIGGER_RE = re.compile(
    r"\b(mass[- ]casualt\w*|casualt\w+|death toll|deaths?|dead|died|fatal\w*|wounded|killed|shot dead|shooting|gunman|massacre|bomb\w*|explosion|blast|"
    r"plane crash|crash(?:es|ed)?|derail\w*|collision|terror\w*|hostages?|airstrike|air strike|missile|invasion|offensive|war|"
    r"attack(?:s|ed)?|assassinat\w*|coup|genocide|chemical attack)\b", re.I)
# Official hazard feeds use fixed titles; a trigger inside them is a hazard word, not a crisis claim.
OFFICIAL_TYPES = {"earthquake", "weather", "volcano", "storm", "flood", "wildfire", "smoke", "tsunami", "space", "drought", "transport", "outage", "recall", "cyber"}


def trigger_of(e):
    """Return the matched trigger word, or None."""
    if e.get("type") in OFFICIAL_TYPES:
        return None
    m = TRIGGER_RE.search("%s %s" % (e.get("title", ""), e.get("place", "")))
    return m.group(0).lower() if m else None


def load_approved(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return set(data if isinstance(data, list) else data.get("ids", []))
    except (OSError, ValueError):
        return set()


def apply(events, approved):
    """Split events into (published, held). Held items carry the reason."""
    out, held = [], []
    for e in events:
        if e.get("curated") and not e.get("auto"):
            out.append(e)      # a person wrote it from named sources (auto items are NOT exempt: no person read them) and checked its wording; the global KILL still applies
            continue
        w = trigger_of(e)
        if w and e["id"] not in approved:
            held.append({"id": e["id"], "title": e["title"][:160], "source": e.get("source", ""), "type": e["type"], "trigger": w})
        else:
            out.append(e)
    return out, held


def global_stop(root):
    return os.path.exists(os.path.join(root, "KILL")) or os.environ.get("BND_KILL") == "1"
