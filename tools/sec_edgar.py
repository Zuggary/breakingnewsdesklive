"""SEC EDGAR 8-K feed (GD8 part 2). Parser only. NOT in SOURCES yet.

Hold: the SEC wants a User-Agent with a contact address. The CoS rule is to use contact@breakingnewsdesklive.com only when it routes.
The MX record points at Gandi mail, but no test message has been sent. Add the feed to SOURCES after the CoS confirms the address.
Fair access: 10 requests per second at most, per user. This feed needs 1 request per minute.
Feed: https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom (count must be 10, 20, 30, 40, 50, 60, 70, 80, 90, 100 or 500).
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = "breakingnewsdesklive/1.0 (+https://breakingnewsdesklive.com/about; contact@breakingnewsdesklive.com)"
FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom"
NS = {"a": "http://www.w3.org/2005/Atom"}
MAX_ITEMS = 10


def parse_atom(xml_text):
    """Return a list of {company, cik, filed (iso utc), url, accession} for 8-K entries, newest first, at most MAX_ITEMS."""
    root = ET.fromstring(xml_text)
    out = []
    for en in root.findall("a:entry", NS):
        title = (en.findtext("a:title", "", NS) or "").strip()
        m = re.match(r"^8-K[^-]*-\s*(.+?)\s*\((\d{10})\)", title)
        if not m:
            continue
        link = en.find("a:link", NS)
        url = link.get("href") if link is not None else ""
        upd = (en.findtext("a:updated", "", NS) or "").strip()
        try:
            dt = datetime.fromisoformat(upd.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        acc = re.search(r"(\d{10}-\d{2}-\d{6})", (en.findtext("a:summary", "", NS) or "") + url)
        if url.startswith("https://www.sec.gov/"):
            out.append({"company": m.group(1), "cik": m.group(2), "filed": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "url": url, "accession": acc.group(1) if acc else ""})
    out.sort(key=lambda x: x["filed"], reverse=True)
    return out[:MAX_ITEMS]
