"""Fail-closed ingestion of externally prepared desk items. Standard library only."""
import json
from datetime import timedelta
from urllib.parse import urlsplit

from tools import claims, manual_items


def load(path):
    """Read an item list; absent, unreadable or invalid files contain no items."""
    try:
        with open(path, encoding="utf-8") as stream:
            items = json.load(stream)
        return items if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def gate(item, now):
    """Return every publication problem; malformed external data fails closed."""
    if not isinstance(item, dict):
        return ["item must be an object"]
    try:
        bad = manual_items.validate(item)
        if bad:
            return bad
        if not isinstance(item["id"], str) or not item["id"].startswith("auto-"):
            bad.append("id must start with auto-")
        # Require usable named sources even when extra sources are not evidence.
        origins = set()
        if not isinstance(item["sources"], list) or not isinstance(item["responses"], list):
            return bad + ["sources and responses must be lists"]
        for source in item["sources"]:
            if not isinstance(source.get("source"), str) or not source["source"]:
                bad.append("source needs a name")
            url = source.get("url", "")
            parsed = urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                bad.append("source needs an absolute web URL")
                continue
            if source.get("kind") == "outlet" and source.get("verification") == "attributed":
                origins.add(claims.origin_of(parsed.hostname))
        origins.discard("unknown")
        if len(origins) < 2:
            bad.append("need two attributed outlet sources with distinct origins")
        if not item["responses"]:
            bad.append("missing responses")
        if "The desk has not confirmed it." not in item["summary"]:
            bad.append("missing desk confirmation disclaimer")
        when = manual_items.parse(item["time"])
        expires = manual_items.parse(item["expires"])
        if expires <= now:
            bad.append("expired")
        if when > now + timedelta(hours=1):
            bad.append("time more than one hour in the future")
        if expires - when > timedelta(hours=72):
            bad.append("validity exceeds 72 hours")
        # Exercise the shared conversion too: malformed optional fields must not
        # make one external item abort publication of the remaining items.
        manual_items.to_event(item, now)
        return bad
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return ["malformed item"]


def active(items, now):
    """At most ten passing items, newest first."""
    return sorted((item for item in items if not gate(item, now)),
                  key=lambda item: manual_items.parse(item["time"]), reverse=True)[:10]
