"""Automatic major-news proposals (GD8). INTERNAL. Reads tip-watcher leads and proposes curated items. Plain code plus an optional on-device model.

Gates. A proposal is `ready` only when ALL hold:
  - 2 or more TOP outlets (the tip feeds: Al Jazeera, BBC, CBS, CNN, Guardian, NBC, NPR) report the story. GDELT domains do not count here.
  - An official response line is found in the headlines (White House, Pentagon, FBI, DHS, police ... says, denies, no credible ...).
  - The summary is our own wording: a model-free template, or one short sentence from the on-device model that passes the word guard.
  - The item passes manual_items.validate (no alarm words, DC not Washington, official response present).
Label: always one shared outlet chain, so the label is "Unverified lead", shown as "Reported by X · response". Only a person who reads a primary
source can lift it. A ready proposal still goes live only when it is copied into manual_items.json and pushed through the guarded path.
"""
import re
from datetime import datetime, timedelta, timezone

from tools import manual_items, lib

TOP_OUTLETS = {"aljazeera": "Al Jazeera", "bbc": "BBC News", "cbs": "CBS News", "cnn": "CNN", "guardian": "The Guardian", "nbc": "NBC News", "npr": "NPR"}
RESPONSE_CLAUSE_RX = re.compile(
    r"\b((?:White House|Pentagon|State Department|FBI|DHS|Homeland Security|CIA|Secret Service|Justice Department|FAA|police|Iran|Israel|Russia|China|Kremlin|[A-Z][a-z]+ government)\s+"
    r"(?:says|said|denies|denied|confirms|confirmed|rejects|rejected|calls|called)\s+[^,;:.–—\-]{3,90})", re.I)
HOURS_VALID = 48


def response_lines(titles):
    """Official or party response clauses found in headlines. Returns [(who, text)]."""
    out = []
    for t in titles:
        for m in RESPONSE_CLAUSE_RX.finditer(t):
            clause = re.split(r"\s+(?:after|as|amid|following|over|while|but)\s+", " ".join(m.group(1).split()), maxsplit=1)[0]
            parts = re.split(r"\s+(says|said|denies|denied|confirms|confirmed|rejects|rejected|calls|called)\s+", clause, maxsplit=1, flags=re.I)
            if len(parts) == 3:
                out.append((parts[0], (parts[1].lower() if parts[1].lower() in ("denies", "denied", "confirms", "confirmed", "rejects", "rejected") else "says") + " " + parts[2].strip()))
    seen, uniq = set(), []
    for w, tx in out:
        if (w.lower(), tx.lower()) not in seen:
            seen.add((w.lower(), tx.lower()))
            uniq.append((w, tx))
    return uniq[:3]


def template_summary(outlets, topic_words):
    names = ", ".join(TOP_OUTLETS[o] for o in outlets)
    return "%s report on this story. The reports are listed with their sources. The desk has not confirmed it." % names


def word_guard(summary, titles):
    """Every capitalised word and every number in a model sentence must appear in the cluster headlines."""
    blob = " ".join(titles).lower()
    for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", summary):
        if w.lower() not in blob and w not in ("The", "This", "These", "Reported", "Officials", "Report", "Reports"):
            return False
    return all(n in blob for n in re.findall(r"\d+", summary))


def propose(candidate, now, model_sentence=None):
    """candidate: one entry of tipwatch.security_candidates(). Returns {ready, reasons, item}."""
    titles = [i["title"] for i in candidate["items"]]
    top = sorted({i["feed"] for i in candidate["items"] if i["feed"] in TOP_OUTLETS})
    reasons = []
    if len(top) < 2:
        reasons.append("fewer than 2 top outlets (%d)" % len(top))
    resp = response_lines(titles)
    if not resp:
        reasons.append("no official response line in the headlines")
    summary = template_summary(top or ["unknown"], [])
    if model_sentence:
        s = model_sentence(titles)
        if s and word_guard(s, titles) and not manual_items.ALARM_RE.search(s) and lib.claims_ok(s):
            summary = s.strip() + " " + "The desk has not confirmed it."
    first = candidate["first_seen"]
    t0 = datetime.strptime(first, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    item = {
        "id": "auto-" + candidate["lead"], "title": "Reported by %s (%s). %s" % (" and ".join(TOP_OUTLETS[o] for o in top[:3]) or "outlets", ", ".join(topic_words(titles)) or "security story", (resp[0][0] + " " + resp[0][1]) if resp else "No official response found"),
        "place": "United States", "time": first, "expires": (t0 + timedelta(hours=HOURS_VALID)).strftime("%Y-%m-%dT%H:%M:%SZ"), "severity": "moderate",
        "summary": summary,
        "sources": [{"source": "outlet chain (unconfirmed)", "intermediary": None, "url": "", "published": first, "scope": ", ".join(TOP_OUTLETS[o] for o in top), "verification": "attributed", "kind": "outlet"}],
        "responses": [{"who": w, "text": tx, "verification": "attributed"} for w, tx in resp],
        "carried_by": [TOP_OUTLETS[o] for o in top],
        "links_to_read": [i["link"] for i in candidate["items"][:6]],
    }
    problems = manual_items.validate(item) if resp else ["no responses"]
    reasons += [p for p in problems if p not in ("missing responses",) or not resp]
    return {"ready": not reasons, "reasons": reasons, "item": item}


def topic_words(titles, limit=4):
    """Neutral topic words: the security terms and the proper nouns that two or more headlines share. No headline text is copied."""
    from tools import tipwatch
    seen = []
    for t in titles:
        for m in tipwatch.SECURITY_RX.finditer(t):
            w = m.group(0).lower()
            if w not in seen:
                seen.append(w)
    caps = {}
    for t in titles:
        for w in set(re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", t)):
            caps[w] = caps.get(w, 0) + 1
    names = [w for w, n in sorted(caps.items(), key=lambda x: -x[1]) if n >= 2 and w not in ("The", "This", "That", "Says", "Report", "Reports", "After", "Over", "Washington")]   # Washington is ambiguous: a person adds DC
    return (names + seen)[:limit]
