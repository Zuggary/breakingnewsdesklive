"""GD8 part 3: claim labels, evidence chains and the ticker gate. Plain code, no model calls.

Labels, lowest to highest evidence:
  Unverified lead            no independent chain, or one chain that is not official
  Official single source     one chain, and it is an official statement
  Corroborated               2 or more independent evidence chains for the same claim
  Contested / Corrected / Resolved   set by a person or by a later report; they win over the evidence labels
Precedence when labels conflict: Corrected, Contested, Resolved, Corroborated, Official single source, Unverified lead.

Evidence chain = one origin. Copies, reposts, syndicated articles and sister outlets of one origin are ONE chain.
An unknown origin counts as the same chain as every other unknown origin: two links never corroborate each other by default.
A lead (a social post, a live-stream tip, a tip feed) is never evidence.
Our own probe measurement is a chain for a page-error claim only. It does not prove a cause.
"""
from datetime import timezone

UNVERIFIED = "Unverified lead"
OFFICIAL = "Official single source"
CORROBORATED = "Corroborated"
CONTESTED = "Contested"
CORRECTED = "Corrected"
RESOLVED = "Resolved"
PRECEDENCE = [CORRECTED, CONTESTED, RESOLVED, CORROBORATED, OFFICIAL, UNVERIFIED]

EVIDENCE_KINDS = ("official", "outlet", "measurement")      # these can be a chain
LEAD_KINDS = ("lead",)                                      # these never can

# Outlets that share one newsroom, wire or owner. Their stories are one chain.
ORIGIN_GROUPS = {
    "cox-media": ["wftv.com", "wsoctv.com", "kiro7.com", "wpxi.com", "whio.com", "wokv.com", "wgauradio.com", "wsbtv.com", "ksat.com"],
    "yahoo-aol": ["aol.com", "aol.co.uk", "yahoo.com", "news.yahoo.com", "finance.yahoo.com"],
    "iheart": ["iheart.com", "1073theeagle.com"],
    "tegna": ["kare11.com", "wfaa.com", "king5.com", "kvue.com", "wusa9.com"],
    "scripps": ["wtvf.com", "click2houston.com", "wxyz.com", "kjrh.com"],
    "gannett": ["usatoday.com", "freep.com", "indystar.com"],
    "ap-wire": ["apnews.com"],
}
_DOMAIN_TO_GROUP = {d: g for g, ds in ORIGIN_GROUPS.items() for d in ds}


def origin_of(domain, stated=None):
    """The origin id for an outlet domain. `stated` is an origin named in the story (a wire or an agency). Unknown -> 'unknown'."""
    if stated:
        return stated.lower()
    d = (domain or "").lower().replace("www.", "")
    if not d:
        return "unknown"
    return _DOMAIN_TO_GROUP.get(d, d)


def chains(claim, kinds=EVIDENCE_KINDS):
    """The set of independent origins that support the claim. Withdrawn evidence and leads are not counted."""
    out = set()
    for ev in claim.get("evidence", []):
        if ev.get("withdrawn") or ev.get("kind") not in kinds:
            continue
        o = ev.get("origin") or "unknown"
        out.add(o)
    return out


def label(claim):
    """The current label of a claim, by the precedence list."""
    flags = claim.get("flags", {})
    if flags.get("corrected"):
        return CORRECTED
    if flags.get("contested"):
        return CONTESTED
    if flags.get("resolved"):
        return RESOLVED
    cs = chains(claim)
    # A measurement chain counts only for a page-error claim.
    if claim.get("type") != "page-error":
        cs = chains(claim, ("official", "outlet"))
    if len(cs) >= 2:
        return CORROBORATED
    if len(cs) == 1:
        official = [e for e in claim.get("evidence", []) if not e.get("withdrawn") and e.get("kind") == "official"]
        return OFFICIAL if official else UNVERIFIED
    return UNVERIFIED


def revise(claim, now, why=""):
    """Recompute the label. When it changes, append one history record. Returns True when it changed."""
    new = label(claim)
    old = claim.get("label")
    if new != old:
        claim.setdefault("history", []).append({"t": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "from": old, "to": new, "why": why})
        claim["label"] = new
        return True
    return False


def add_evidence(claim, kind, origin, url, now, text=""):
    claim.setdefault("evidence", []).append({"kind": kind, "origin": origin or "unknown", "url": url, "t": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "text": text})
    return revise(claim, now, "evidence added (%s)" % kind)


def withdraw(claim, origin, now):
    """Withdraw every piece of evidence from one origin. The claim drops a level when the chain count falls."""
    for ev in claim.get("evidence", []):
        if (ev.get("origin") or "unknown") == origin:
            ev["withdrawn"] = True
    return revise(claim, now, "evidence from %s withdrawn" % origin)


def set_flag(claim, name, now, note=""):
    claim.setdefault("flags", {})[name] = True
    if note:
        claim.setdefault("notes", []).append(note)
    return revise(claim, now, "flag %s set" % name)


def ticker_ok(claim, strict=True):
    """Only Corroborated claims go to the ticker and the narration queue. Official single source is allowed only when strict is False."""
    lab = claim.get("label") or label(claim)
    if lab == CORROBORATED:
        return True
    return (not strict) and lab == OFFICIAL


class Queue:
    """The narration and ticker queue. It holds only claims that pass ticker_ok. It follows the claims on every sync."""

    def __init__(self):
        self.entries = {}

    def sync(self, claims, now, strict=True):
        """Add passing claims, replace changed ones with a 'what changed' line, remove claims that no longer pass. Returns the changes."""
        changes = []
        for c in claims:
            cid = c["id"]
            ok = ticker_ok(c, strict)
            cur = self.entries.get(cid)
            if ok and not cur:
                self.entries[cid] = {"id": cid, "text": c["text"], "label": c["label"], "what_changed": ""}
                changes.append(("added", cid))
            elif ok and cur and (cur["text"] != c["text"] or cur["label"] != c["label"]):
                self.entries[cid] = {"id": cid, "text": c["text"], "label": c["label"],
                                     "what_changed": "Changed from \"%s\" (%s) to \"%s\" (%s) at %s." % (cur["text"], cur["label"], c["text"], c["label"], now.strftime("%H:%M UTC"))}
                changes.append(("replaced", cid))
            elif not ok and cur:
                del self.entries[cid]
                changes.append(("removed", cid))
        for cid in [k for k in self.entries if k not in {c["id"] for c in claims}]:
            del self.entries[cid]
            changes.append(("removed", cid))
        return changes


def claim_from_news_item(item, probe_snapshot=None, now=None):
    """Build a claim from a News reports item (tools/news_lane.py). Each outlet link is evidence; sister outlets share one chain."""
    cl = {"id": "claim-" + item["id"], "type": "page-error", "text": item["title"].replace("News reports: ", ""), "evidence": [], "flags": {}}
    domains = (item.get("detail") or {}).get("outlet_domains") or [l["label"] for l in item.get("links", [])]
    for dm in domains:
        cl["evidence"].append({"kind": "outlet", "origin": origin_of(dm), "url": "", "t": item["time"], "text": ""})
    for p in (item.get("detail") or {}).get("probes", []):
        cl["evidence"].append({"kind": "measurement", "origin": "desk-probe-" + p["service"], "url": "", "t": p["since"], "text": "%s %s" % (p["service"], p["status"])})
    cl["label"] = label(cl)
    return cl


OFFICIAL_TYPES = {"earthquake", "weather", "volcano", "storm", "flood", "wildfire", "smoke", "tsunami", "space", "drought", "transport", "aviation", "recall", "cyber", "notice", "statement"}
STRICT_TICKER = True


def confidence_for_event(e):
    """The label for a built event. News items and probe items use their evidence. Official feeds are one official chain.
    Outlet headline groups use the origins of their outlets."""
    d = e.get("detail") or {}
    lane = d.get("lane")
    if lane == "news":
        return label(claim_from_news_item(e))
    if lane == "probes":
        return UNVERIFIED if e.get("detail", {}).get("open", True) else RESOLVED
    if e.get("type") == "headline":
        origins = {origin_of(l.get("label")) for l in e.get("links", [])} or {"unknown"}
        origins.discard("unknown")
        return CORROBORATED if len(origins) >= 2 else UNVERIFIED
    if e.get("type") in OFFICIAL_TYPES or e.get("source_id") in ("ms365",) or str(e.get("source_id", "")).startswith("status-"):
        return OFFICIAL
    return UNVERIFIED
