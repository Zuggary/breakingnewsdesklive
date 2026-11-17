"""The lead story feed (data/lead-story.json). Built for a stream VJ or any reader program: one lead story, a short list of next stories.

Each story: headline, a 2-line factual summary, the confidence label, sources (name, intermediary, link; never an outlet's headline),
as_of (when the feed was built) and updated (when the event happened or last changed). Plain code.
The lead is the first of: a big grouped item, a curated item, a News reports item, then the top ranked event.
"""
import re

KIND_ORDER = ("big", "curated", "news")


def two_lines(summary, limit=240):
    """The first two sentences, at most `limit` characters."""
    parts = re.split(r"(?<=[.!?])\s+", (summary or "").strip())
    out = " ".join(parts[:2]).strip()
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;") + "..."
    return out


def kind_of(e):
    if e.get("big"):
        return "big"
    d = e.get("detail") or {}
    if d.get("lane") == "curated" or e.get("curated"):
        return "curated"
    if d.get("lane") == "news":
        return "news"
    return "event"


def sources_of(e):
    """Source names and links only. A News reports item lists outlet names and links, never their headlines."""
    d = e.get("detail") or {}
    out = []
    if d.get("lane") == "curated":
        for s in d.get("sources", []):
            out.append({"name": s.get("source"), "intermediary": s.get("intermediary"), "url": None})
        urls = {l.get("label"): l.get("url") for l in e.get("links", [])}
        for s in out:
            s["url"] = urls.get(s["name"])
    elif d.get("lane") == "news":
        for l in e.get("links", [])[:6]:
            out.append({"name": l.get("label"), "intermediary": None, "url": l.get("url")})
    else:
        out.append({"name": e.get("source"), "intermediary": None, "url": e.get("source_url")})
    return out


def story(e):
    d = e.get("detail") or {}
    return {"id": e["id"], "kind": kind_of(e), "headline": e["title"], "summary": two_lines(e.get("summary")), "label": e.get("confidence"),
            "reported_line": d.get("reported_line"), "place": e.get("place"), "severity": e.get("severity"), "sources": sources_of(e),
            "updated": e.get("time"), "ticker_ok": bool(e.get("ticker_ok"))}


def build(events, generated, n_next=4):
    """events must already be ranked (build_data.rank_key). Returns the feed dict."""
    if not events:
        return {"generated": generated, "as_of": generated, "lead": None, "next": [], "note": "No events."}
    ranked = []
    for k in KIND_ORDER:
        ranked += [e for e in events if kind_of(e) == k and e not in ranked]
    ranked += [e for e in events if e not in ranked]
    lead = ranked[0]
    nxt = [e for e in ranked[1:1 + n_next]]
    return {"generated": generated, "as_of": generated, "lead": story(lead), "next": [story(e) for e in nxt],
            "note": "Attributed facts only. Read the label with every story. Reported is not confirmed. Official responses are in reported_line."}
