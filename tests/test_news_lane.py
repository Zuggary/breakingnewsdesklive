"""GD7 part B: the News reports lane. Replay of the 16 Nov 2026 bank login outage (synthetic fixture, fictional outlets)."""
import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import news_lane, probes, lib  # noqa: E402

SERVICES = json.load(open(os.path.join(ROOT, "tools", "probe_list.json")))
REPLAY = json.load(open(os.path.join(ROOT, "tests", "fixtures", "replay-2026-11-16.json")))["articles"]
NOW = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)


class Matching(unittest.TestCase):
    def test_outage_headlines_match_a_service(self):
        self.assertEqual(news_lane.match("Chase customers report problems logging in to the mobile app"), ["chase"])
        self.assertEqual(sorted(news_lane.match("Wells Fargo says some customers unable to log in, Chase also reporting problems")), ["chase", "wellsfargo"])
        self.assertIn("bofa", news_lane.match("Bank of America app not working for some customers"))
        self.assertIn("usbank", news_lane.match("U.S. Bank online banking down for many customers"))
        self.assertIn("venmo", news_lane.match("Venmo outage leaves users unable to send money"))
        self.assertIn("att", news_lane.match("AT&T outage reported across several states"))

    def test_question_and_issue_wording_matches(self):
        self.assertIn("zelle", news_lane.match("Is Your Bank Down? Chase, Wells Fargo, Zelle users report issues"))
        self.assertIn("zelle", news_lane.match("Are banks down? Chase, Bank of America, Zelle customers have problems"))
        self.assertEqual(news_lane.match("Zelle shares plans for new app"), [])

    def test_common_words_do_not_match(self):
        for t in ("Police chase suspect through downtown after shooting", "United we stand: community rallies after the storm",
                  "Delta variant cases fall, officials say", "Bank of America opens 10 new branches", "Discover the best coffee in town", "Chase stars in new film, outage of talent at studio"):
            self.assertEqual(news_lane.match(t), [], t)

    def test_a_service_name_alone_is_not_enough(self):
        self.assertEqual(news_lane.match("Chase Bank announces new savings rates"), [])


class Lane(unittest.TestCase):
    def items(self, arts=REPLAY, snap=None):
        return news_lane.build_items(news_lane.collect(arts), SERVICES, NOW, snap)

    def test_replay_gives_one_grouped_item_with_label_and_links(self):
        items = self.items()
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["title"], "News reports: problems reported at 3 banks, 3 outlets")
        self.assertIn(news_lane.LABEL, it["summary_override"])
        self.assertEqual(it["detail"]["label"], news_lane.LABEL)
        self.assertTrue(it["big"])
        self.assertEqual(it["detail"]["outlets"], 3)
        self.assertTrue(it["links"])
        for l in it["links"]:
            self.assertTrue(l["url"].startswith("https://"))
            self.assertLessEqual(len(l["title"]), 140)

    def test_item_holds_no_article_text(self):
        it = self.items()[0]
        self.assertEqual(set(it["links"][0]), {"label", "title", "url"})
        self.assertNotIn("body", json.dumps(it).lower())

    def test_one_outlet_is_not_enough(self):
        one = [a for a in REPLAY if a["domain"] == "wire-one.example"]
        self.assertEqual(self.items(one), [])

    def test_reports_more_than_60_minutes_apart_do_not_group(self):
        a = dict(REPLAY[0]); b = dict(REPLAY[1], seendate="20261116T150500Z")   # 57 minutes later: ok
        self.assertEqual(len(self.items([a, b])), 1)
        b = dict(REPLAY[1], seendate="20261116T152000Z")                         # 72 minutes later: no
        self.assertEqual(self.items([a, b]), [])

    def test_probe_result_is_attached_when_one_exists(self):
        snap = {"generated": probes.iso(NOW), "services": [
            {"id": "chase", "name": "Chase", "group": "bank", "status": "down", "since": "2026-11-16T14:00:00Z", "last_probe": probes.iso(NOW), "last_code": 503, "last_ms": 80}], "incidents": []}
        it = self.items(snap=snap)[0]
        self.assertEqual(it["detail"]["probes"][0]["service"], "Chase")
        self.assertIn("9:00 AM ET", it["summary_override"])

    def test_two_outlets_make_a_plain_not_big_item(self):
        two = [a for a in REPLAY if a["domain"] in ("wire-one.example", "metro-daily.example")]
        it = self.items(two)[0]
        self.assertFalse(it["big"])
        self.assertEqual(it["severity"], "moderate")

    def test_summary_passes_the_fact_gate(self):
        it = self.items()[0]
        ev = dict(it, summary=it["summary_override"])
        self.assertTrue(lib.guard_ok(it["summary_override"], ev), it["summary_override"])
        self.assertTrue(lib.claims_ok(it["summary_override"]))


class Kinds(unittest.TestCase):
    def test_bank_and_airline_stories_are_separate_items(self):
        air = [
            {"url": "https://wire-two.example/ua1", "title": "United Airlines says it has a widespread system outage", "seendate": "20261116T145000Z", "domain": "wire-two.example"},
            {"url": "https://metro-daily.example/ua2", "title": "United Airlines hit by widespread system outage, flights affected", "seendate": "20261116T145500Z", "domain": "metro-daily.example"},
            {"url": "https://radio-hub.example/ua3", "title": "United Airlines faces systems outage", "seendate": "20261116T150000Z", "domain": "radio-hub.example"}]
        items = news_lane.build_items(news_lane.collect(REPLAY + air), SERVICES, NOW, None)
        self.assertEqual(len(items), 2)
        titles = sorted(i["title"] for i in items)
        self.assertEqual(titles, ["News reports: United Airlines problems reported by 3 outlets", "News reports: problems reported at 3 banks, 3 outlets"])
        ua = next(i for i in items if "United" in i["title"])
        self.assertTrue(ua["big"])
        self.assertTrue(all("United" in l["title"] for l in ua["links"]))


class Resolution(unittest.TestCase):
    def test_resolution_reports_from_2_outlets_are_noted(self):
        air = [
            {"url": "https://wire-two.example/ua1", "title": "United Airlines says it has a widespread system outage", "seendate": "20261116T145000Z", "domain": "wire-two.example"},
            {"url": "https://metro-daily.example/ua2", "title": "United Airlines hit by widespread system outage", "seendate": "20261116T145500Z", "domain": "metro-daily.example"},
            {"url": "https://wire-two.example/ua3", "title": "United says tech issue is fixed, departures resuming", "seendate": "20261116T153000Z", "domain": "wire-two.example"},
            {"url": "https://radio-hub.example/ua4", "title": "United Airlines flights resuming after technical issue is resolved", "seendate": "20261116T153500Z", "domain": "radio-hub.example"}]
        it = news_lane.build_items(news_lane.collect(air), SERVICES, NOW, None)[0]
        self.assertEqual(it["detail"]["resolution"]["outlets"], 2)
        self.assertIn("fixed or operations resuming", it["summary_override"])
        self.assertIn(news_lane.LABEL, it["summary_override"])
        ev = dict(it, summary=it["summary_override"])
        self.assertTrue(lib.guard_ok(it["summary_override"], ev), it["summary_override"])

    def test_one_resolution_report_is_not_enough(self):
        air = [
            {"url": "https://wire-two.example/ua1", "title": "United Airlines says it has a widespread system outage", "seendate": "20261116T145000Z", "domain": "wire-two.example"},
            {"url": "https://metro-daily.example/ua2", "title": "United Airlines hit by widespread system outage", "seendate": "20261116T145500Z", "domain": "metro-daily.example"},
            {"url": "https://wire-two.example/ua3", "title": "United says tech issue is fixed, departures resuming", "seendate": "20261116T153000Z", "domain": "wire-two.example"}]
        it = news_lane.build_items(news_lane.collect(air), SERVICES, NOW, None)[0]
        self.assertIsNone(it["detail"]["resolution"])

    def test_resolution_headlines_alone_make_no_item(self):
        only = [{"url": "https://a.example/x", "title": "United says tech issue is fixed, departures resuming", "seendate": "20261116T153000Z", "domain": "a.example"},
                {"url": "https://b.example/x", "title": "United Airlines flights resuming after issue resolved", "seendate": "20261116T153500Z", "domain": "b.example"}]
        self.assertEqual(news_lane.build_items(news_lane.collect(only), SERVICES, NOW, None), [])


class TopSlot(unittest.TestCase):
    def test_replayed_event_takes_the_top_slot_in_the_built_data(self):
        from tools import build_data
        fx = os.path.join(ROOT, "tests", "fixtures")
        base = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        arts = [dict(a, seendate=(base - timedelta(minutes=90 - 5 * i)).strftime("%Y%m%dT%H%M%SZ")) for i, a in enumerate(REPLAY[:6])]
        build_data.NEWS_ARTICLES = []
        orig = build_data.parse_gdelt
        def parse_with_news(d, src):
            out = orig(d, src)
            build_data.NEWS_ARTICLES = arts
            return out
        build_data.PARSERS["gdelt-doc"] = parse_with_news
        try:
            events, status = build_data.build(fx, base)
        finally:
            build_data.PARSERS["gdelt-doc"] = orig
        self.assertTrue(events[0].get("big"))
        news = [e for e in events if e["source_id"] == "news-lane"]
        self.assertEqual(len(news), 1)
        self.assertEqual(news[0]["type"], "outage")          # outage items stay on the stream; headline items do not
        self.assertTrue(next(s for s in status if s["id"] == "news-lane")["ok"])


class NoModelCalls(unittest.TestCase):
    def test_news_lane_imports_no_model_client(self):
        src = open(os.path.join(ROOT, "tools", "news_lane.py"), encoding="utf-8").read()
        imports = " ".join(re.findall(r"^\s*(?:import|from)\s+(\S+)", src, re.M)).lower()
        for bad in ("anthropic", "openai", "google", "genai", "claude", "gemini", "subprocess", "requests", "urllib"):
            self.assertNotIn(bad, imports)


if __name__ == "__main__":
    unittest.main()
