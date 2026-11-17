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
LEAD_KINDS = ("lead", "user-reports")                        # these never can. user-reports covers Downdetector-style counts: reports by users, never proof

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
        # One official chain counts as "Official single source" only when we read the primary source ourselves.
        # "United says it is fixed, via CBS" stays a lead until the airline's own statement is read.
        official = [e for e in claim.get("evidence", []) if not e.get("withdrawn") and e.get("kind") == "official" and e.get("verification", "direct") == "direct"]
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


def stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_evidence(kind, source, url, observed, intermediary=None, published=None, scope=None, verification=None, text=""):
    """One piece of evidence with its fields kept apart (CoS lesson from the Agenda-Free coverage):
    source        the ORIGINAL source of the statement or fact (United Airlines, the FAA, a company, a person)
    intermediary  who passed it on (a Reuters reporter posting United's statement). May be None.
    published     when the source said it. observed is when we saw it.
    scope         what the statement covers ("departures only", "all operations", "one airport").
    verification  direct (we read the primary source), attributed (an intermediary says the source said it), tentative.
    The chain is the SOURCE. Two intermediaries who relay one source are one chain."""
    return {"kind": kind, "origin": (source or "unknown"), "source": source or "unknown", "intermediary": intermediary, "url": url,
            "published": published, "observed": stamp(observed), "scope": scope, "verification": verification or ("direct" if kind == "official" and not intermediary else "attributed"),
            "text": text}


def add_evidence(claim, kind, origin, url, now, text="", intermediary=None, published=None, scope=None, verification=None):
    claim.setdefault("evidence", []).append(make_evidence(kind, origin, url, now, intermediary, published, scope, verification, text))
    return revise(claim, now, "evidence added (%s)" % kind)


def note_disappeared(claim, source, now):
    """A notice that was removed from an airline page or newsroom. This is NOT a resolution.
    The statement existed, so the chain stays. The claim gets a note and a history record, and its label does not change."""
    hit = False
    for ev in claim.get("evidence", []):
        if (ev.get("source") or ev.get("origin")) == source and not ev.get("disappeared"):
            ev["disappeared"] = stamp(now)
            hit = True
    if hit:
        claim.setdefault("notes", []).append("A notice from %s was removed at %s. A removed notice is not a resolution." % (source, now.strftime("%H:%M UTC")))
        claim.setdefault("history", []).append({"t": stamp(now), "from": claim.get("label"), "to": claim.get("label"), "why": "notice from %s disappeared (not a resolution)" % source})
    return hit


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


class TipQueue:
    """Chat and stream tips wait here until a person or a check has verified them. Nothing in this queue airs.
    A tip becomes evidence only through promote(), which needs a primary or independent source."""

    def __init__(self):
        self.tips = {}

    def queue(self, tid, text, channel, now):
        self.tips[tid] = {"id": tid, "text": text, "channel": channel, "queued": stamp(now), "state": "queued", "claim": None}

    def promote(self, tid, claim, kind, source, url, now, **kw):
        """Attach a checked, independent piece of evidence for the tip's claim. The tip itself is not evidence."""
        t = self.tips[tid]
        if kind in LEAD_KINDS:
            raise ValueError("a lead cannot be promoted as evidence")
        add_evidence(claim, kind, source, url, now, **kw)
        t["state"], t["claim"] = "checked", claim["id"]

    def airable(self):
        return []     # tips never air. Claims air, through the ticker gate.


# Where to look for one service together: airline social, the newsroom and the wires. Names only. Our own code reads
# newsrooms and feeds that allow it; social accounts are read by a person or through a permitted API.
WATCH = {
    "united": {"social": ["United Airlines official account"], "newsroom": ["united.com/en/us/newsroom", "hub.united.com"], "wires": ["AP", "Reuters"], "official_status": ["FAA NAS status"]},
    "delta": {"social": ["Delta official account"], "newsroom": ["news.delta.com"], "wires": ["AP", "Reuters"], "official_status": ["FAA NAS status"]},
    "american": {"social": ["American Airlines official account"], "newsroom": ["news.aa.com"], "wires": ["AP", "Reuters"], "official_status": ["FAA NAS status"]},
    "southwest": {"social": ["Southwest official account"], "newsroom": ["swamedia.com"], "wires": ["AP", "Reuters"], "official_status": ["FAA NAS status"]},
}


def watch_plan(service_id):
    """Everything to check together for one service. Unknown services get the wires only."""
    return WATCH.get(service_id, {"social": [], "newsroom": [], "wires": ["AP", "Reuters"], "official_status": []})
