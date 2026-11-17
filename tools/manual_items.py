"""Curated items (GD8): a person writes a short item in our own words from named sources. The item is labelled by the claim rules.

File: manual_items.json in the repo root, a list of items. Each item needs:
  id, title, place, lat, lon, time (UTC), expires (UTC), severity, summary (our own wording),
  sources   [{source, intermediary, url, published, scope, verification, kind}]   (kind: outlet | official)
  responses [{who, text, verification}]   the official response lines. REQUIRED for a security or national-news item.
The first source is the original source of the story. Outlets that only carry it name it as `source` too, so they are one chain.
Rules: no alarm words, no copied headline, a place with a state or "DC" when the name could mean two places.
"""
import re
from datetime import datetime, timezone

from tools import claims, lib

ALARM_RE = re.compile(r"\b(plot(?:s|ting|ted)?|terrifying|terrify\w*|imminent|breaking|shock\w*|panic|chaos|massive|horrific|bombshell|explosive)\b", re.I)
REQUIRED = ("id", "title", "place", "time", "expires", "severity", "summary", "sources", "responses")   # lat and lon are optional


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def validate(it):
    """Return a list of problems. Empty means the item may be published."""
    bad = []
    for k in REQUIRED:
        if k not in it or it[k] in (None, "", []):
            bad.append("missing " + k)
    if bad:
        return bad
    text = " ".join([it["title"], it["summary"]] + [r["text"] for r in it["responses"]])
    text = re.sub(r"\b(?:not|no)\s+(?:an\s+)?imminent\b", "", text, flags=re.I)   # 'not an imminent attack' is calm wording
    if ALARM_RE.search(text):
        bad.append("alarm wording: " + ALARM_RE.search(text).group(0))
    if not lib.claims_ok(it["summary"]):
        bad.append("blame, suspect or casualty wording in the summary")
    norm = text.replace("D.C.", "DC")
    if re.search(r"\bWashington\b(?!,? DC\b)", norm):
        bad.append("Washington must say DC")
    if not any(s.get("source") for s in it["sources"]):
        bad.append("no named source")
    for r in it["responses"]:
        if not r.get("who") or not r.get("text"):
            bad.append("response needs who and text")
    try:
        if parse(it["expires"]) <= parse(it["time"]):
            bad.append("expires before time")
    except ValueError:
        bad.append("bad time format")
    return bad


def reported_line(it):
    """One plain line: who reported it (every named source), then each official response."""
    who = " and ".join(s["source"] + (" (%s)" % s["scope"] if s.get("scope") else "") for s in it["sources"][:3])
    return " \u00b7 ".join(["Reported by " + who] + ["%s: %s" % (r["who"], r["text"]) for r in it["responses"]])


def to_event(it, now):
    """A site event. The label comes from the evidence: one original source means 'Unverified lead' (shown as Reported by ...)."""
    cl = {"id": "claim-" + it["id"], "type": "story", "text": it["title"], "evidence": [], "flags": {}}
    for s in it["sources"]:
        claims.add_evidence(cl, s.get("kind", "outlet"), s["source"], s.get("url", ""), now, intermediary=s.get("intermediary"),
                            published=s.get("published"), scope=s.get("scope"), verification=s.get("verification"))
    ev = {
        "id": it["id"], "type": "security", "title": it["title"], "place": it["place"], "lat": it.get("lat"), "lon": it.get("lon"),
        "time": it["time"], "severity": it["severity"], "size": len(set(s["source"] for s in it["sources"])),
        "source": "Desk (curated from named sources)", "source_id": "curated", "source_url": it["sources"][0].get("url") or "https://breakingnewsdesklive.com/about",
        "detail": {"lane": "curated", "open": True, "reported_line": reported_line(it), "label": cl["label"],
                   "responses": it["responses"], "sources": [{k: s.get(k) for k in ("source", "intermediary", "scope", "verification", "published")} for s in it["sources"]],
                   "carried_by": it.get("carried_by", []), "expires": it["expires"]},
        "links": [{"label": s["source"], "title": "Source: " + s["source"] + (" via " + s["intermediary"] if s.get("intermediary") else ""), "url": s["url"]} for s in it["sources"] if s.get("url", "").startswith("https://")],
        "region": it.get("region", "Americas"), "summary_override": it["summary"], "curated": True,
    }
    return ev


def active(items, now):
    out = []
    for it in items:
        if validate(it):
            continue
        if parse(it["time"]) <= now <= parse(it["expires"]):
            out.append(it)
    return out
