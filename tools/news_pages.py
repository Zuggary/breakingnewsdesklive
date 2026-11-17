"""Static, attributed news pages and sitemaps. Standard library only."""
import html
import json
import re
import shutil
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET

BASE = "https://breakingnewsdesklive.com"
SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"
NEWS = "http://www.google.com/schemas/sitemap-news/0.9"


def _time(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def slugify(title):
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].rstrip("-") or "news"


def _path(event):
    return "news/%s/%s/" % (quote(str(event["id"]), safe="").replace(".", "%2E"), slugify(event["title"]))


def _modified(event):
    times = [event["time"]]
    if event.get("updated"):
        times.append(event["updated"])
    times.extend(h["t"] for h in event.get("history", []) if h.get("t"))
    return max(times, key=_time)


def changed_since(event):
    history = event.get("history") or []
    if history:
        h = max(history, key=lambda h: _time(h.get("t") or event["time"]))
        when = _time(h.get("t") or event.get("updated") or event["time"]).strftime("%H:%M UTC")
        old, new = h.get("from"), h.get("to")
        if old and new and old != new:
            levels = ["Unverified lead", "Official single source", "Corroborated"]
            direction = "changed"
            if old in levels and new in levels:
                direction = "raised" if levels.index(new) > levels.index(old) else "lowered"
            return "Updated %s: label %s from %s to %s" % (when, direction, old, new)
        return "Updated %s: %s" % (when, h.get("why") or "item updated")
    if event.get("updated"):
        return "Updated %s: item updated" % _time(event["updated"]).strftime("%H:%M UTC")
    return "No changes since first published at %s." % _time(event["time"]).strftime("%H:%M UTC")


def _sources(event):
    # Link titles may be outlet headlines. Only source names are displayed.
    links = event.get("links", [])
    sources = event.get("detail", {}).get("sources") or links
    result = []
    for i, source in enumerate(sources):
        name = source.get("source") or source.get("name") or source.get("label", "Source")
        matching = next((l for l in links if l.get("label") == name), {})
        url = source.get("url") or matching.get("url") or (event.get("source_url") if i == 0 else "")
        try:
            ok = urlsplit(url or "").scheme.lower() in ("http", "https")
        except ValueError:
            ok = False
        if not ok:
            url = ""
        result.append((name, url))
    return result


def _withdrawn(event):
    d = event.get("detail", {})
    return event.get("confidence") == "Corrected" or bool(event.get("withdrawn") or d.get("withdrawn") or event.get("flags", {}).get("withdrawn"))


def render_page(event, now):
    esc = lambda v: html.escape(str(v), quote=True)
    d = event.get("detail", {})
    url = BASE + "/" + _path(event)
    title = event["title"]
    summary = event.get("summary", event.get("summary_override", ""))
    sources = _sources(event)
    expired = event.get("expired") or (d.get("expires") and _time(d["expires"]) < _time(now))
    article = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title,
               "datePublished": event["time"], "dateModified": _modified(event), "mainEntityOfPage": url,
               "publisher": {"@type": "Organization", "name": "Breaking News Desk"},
               "isBasedOn": [u for _, u in sources if u]}
    # JSON is raw script text: HTML entities would corrupt it. Unicode escapes
    # protect the script boundary while preserving valid JSON and original text.
    structured = json.dumps(article, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    source_html = "".join('<li><a href="%s" rel="nofollow noopener">%s</a></li>' % (esc(u), esc(n)) if u else '<li>%s</li>' % esc(n) for n, u in sources)
    responses = "".join('<li>%s: %s</li>' % (esc(r.get("who", "")), esc(r.get("text", ""))) for r in d.get("responses", []))
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s | Breaking News Desk</title>
<link rel="stylesheet" href="/tokens.css"><link rel="stylesheet" href="/style.css">
<link rel="canonical" href="%s"><meta name="description" content="%s">
<meta property="og:title" content="%s"><meta property="og:description" content="%s">
<meta property="og:url" content="%s"><meta property="og:type" content="article">
<meta property="og:site_name" content="Breaking News Desk">%s
<script type="application/ld+json">%s</script></head>
<body><header class="top"><a class="brand" href="/">Breaking News Desk</a></header>
<main class="page"><article><h1>%s</h1><p class="verdict">%s</p>
<p class="dateline">%s · <time datetime="%s">%s</time></p>%s
<p>%s</p><p class="srcline">%s</p><h2>Sources</h2><ul>%s</ul>
<h2>Official responses</h2><ul>%s</ul><p>Changed since: %s</p>
</article></main></body></html>
''' % (esc(title), esc(url), esc(summary), esc(title), esc(summary), esc(url),
       '<meta name="robots" content="noindex">' if _withdrawn(event) else '', structured,
       esc(title), esc(event["confidence"]), esc(event.get("place", "")), esc(event["time"]),
       esc(_time(event["time"]).strftime("%Y-%m-%d %H:%M UTC")),
       '<p>No longer in the live feed</p>' if expired else '', esc(summary), esc(d["reported_line"]),
       source_html, responses, esc(changed_since(event)))


def build_news(events, expired_events, out_dir, now):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_events = {}
    for items, expired in ((expired_events, True), (events, False)):
        for event in items:
            if event.get("detail", {}).get("reported_line") and event.get("confidence"):
                all_events[str(event["id"])] = dict(event, expired=expired)
    ET.register_namespace("", SITEMAP)
    ET.register_namespace("news", NEWS)
    pages, news = ET.Element("{%s}urlset" % SITEMAP), ET.Element("{%s}urlset" % SITEMAP)
    def node(parent, name, value=None, ns=SITEMAP):
        child = ET.SubElement(parent, "{%s}%s" % (ns, name))
        child.text = value
        return child
    urls = []
    for event in all_events.values():
        path = out / _path(event) / "index.html"
        for stale in path.parent.parent.glob("*/"):  # an older slug of the same id must not stay published
            if stale != path.parent and stale.is_dir():
                shutil.rmtree(stale)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_page(event, now), encoding="utf-8")
        url = BASE + "/" + _path(event)
        urls.append(url)
        if not (event.get("confidence") == "Corrected" or _withdrawn(event)):
            entry = node(pages, "url")
            node(entry, "loc", url)
            node(entry, "lastmod", _modified(event))
        if _time(now) - timedelta(hours=48) <= _time(event["time"]) <= _time(now) and not _withdrawn(event):
            entry = node(news, "url")
            node(entry, "loc", url)
            item = node(entry, "news", ns=NEWS)
            publication = node(item, "publication", ns=NEWS)
            node(publication, "name", "Breaking News Desk", NEWS)
            node(publication, "language", "en", NEWS)
            node(item, "publication_date", event["time"], NEWS)
            node(item, "title", event["title"], NEWS)
    for filename, tree in (("news-pages.xml", pages), ("news-sitemap.xml", news)):
        ET.ElementTree(tree).write(out / filename, encoding="utf-8", xml_declaration=True)
    # The build restores this archive to keep pages after feed expiry.
    archive = out / "news" / "events.json"
    archive.parent.mkdir(exist_ok=True)
    archive.write_text(json.dumps(list(all_events.values())), encoding="utf-8")
    return urls


def source_freshness(probe_state, now):
    """Accept sources.json (checked) or probes.json (last_probe).

    Without an explicit missed counter, count elapsed ten-minute build slots.
    A failed latest poll counts as one; unknown times do not imply misses.
    """
    rows = probe_state if isinstance(probe_state, list) else probe_state.get("sources", probe_state.get("services", []))
    result = []
    for row in rows:
        missed = row.get("missed")
        if missed is None:
            last = row.get("last_probe") or row.get("checked")
            missed = max(0, int((_time(now) - _time(last)).total_seconds() // 600)) if last else 0
            missed += int(row.get("ok") is False)
        missed = max(0, int(missed))
        result.append({"name": row.get("name", row.get("id", "Source")), "state": "stale" if missed >= 3 else "fresh", "missed": missed})
    return result
