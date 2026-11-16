"""GD8 part 7: the internal TIP watcher. Nothing it reads may reach the published data."""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import tipwatch, build_data, feed_terms  # noqa: E402

FX = os.path.join(ROOT, "tests", "fixtures")
NOW = datetime(2026, 11, 16, 23, 0, tzinfo=timezone.utc)


def read(name):
    return open(os.path.join(FX, name), encoding="utf-8").read()


def fake_fetch(bodies):
    def f(url, headers=None):
        if url.endswith("/robots.txt"):
            return 404, ""
        for k, v in bodies.items():
            if url == k:
                return 200, v
        return 404, ""
    return f


class Parse(unittest.TestCase):
    def test_rss_and_atom_give_headline_link_time_only(self):
        a = tipwatch.parse_feed(read("tip-rss-a.xml"), "a")
        b = tipwatch.parse_feed(read("tip-atom-b.xml"), "b")
        self.assertEqual(len(a), 3)
        self.assertEqual(len(b), 2)
        self.assertEqual(set(a[0]), {"feed", "title", "link", "time"})
        self.assertEqual(a[0]["time"], "2026-11-16T22:40:00Z")
        self.assertEqual(b[0]["time"], "2026-11-16T22:45:00Z")


class Leads(unittest.TestCase):
    def store(self):
        st = {"items": [], "robots": {}}
        tipwatch.add_items(st, tipwatch.parse_feed(read("tip-rss-a.xml"), "a") + tipwatch.parse_feed(read("tip-atom-b.xml"), "b"), NOW)
        return st

    def test_two_outlets_on_one_story_make_a_lead(self):
        leads = tipwatch.build_leads(self.store(), NOW)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["n_outlets"], 2)
        self.assertEqual(leads[0]["topic"], "aviation")
        self.assertIn("Air only when Corroborated", leads[0]["next"])

    def test_one_outlet_makes_no_lead(self):
        st = {"items": [], "robots": {}}
        tipwatch.add_items(st, tipwatch.parse_feed(read("tip-rss-a.xml"), "a"), NOW)
        self.assertEqual(tipwatch.build_leads(st, NOW), [])

    def test_three_outlets_and_unrelated_stories(self):
        st = self.store()
        tipwatch.add_items(st, [{"feed": "c", "title": "United Airlines widespread system outage grounds flights across the country", "link": "https://c.example/ua", "time": "2026-11-16T22:50:00Z"}], NOW)
        leads = tipwatch.build_leads(st, NOW)
        self.assertEqual([l["n_outlets"] for l in leads], [3])

    def test_topics(self):
        for t, topic in (("Chase and Wells Fargo customers locked out of online banking", "finance"), ("Hurricane warning issued for the gulf coast", "weather"),
                         ("Council debates parking rules", "other"), ("Ceasefire talks collapse after strikes", "conflict")):
            self.assertEqual(tipwatch.tag_topic(t), topic, t)

    def test_items_older_than_48_hours_are_dropped(self):
        st = {"items": [], "robots": {}}
        old = {"feed": "a", "title": "Old story", "link": "https://a.example/old", "time": "2026-11-14T20:00:00Z"}
        new = {"feed": "a", "title": "New story", "link": "https://a.example/new", "time": "2026-11-16T22:00:00Z"}
        tipwatch.add_items(st, [old, new], NOW)
        self.assertEqual([i["link"] for i in st["items"]], ["https://a.example/new"])

    def test_dedupe_on_link(self):
        st = {"items": [], "robots": {}}
        it = {"feed": "a", "title": "Story", "link": "https://a.example/x", "time": "2026-11-16T22:00:00Z"}
        tipwatch.add_items(st, [it, dict(it)], NOW)
        tipwatch.add_items(st, [dict(it)], NOW)
        self.assertEqual(len(st["items"]), 1)


class Robots(unittest.TestCase):
    def test_404_allows_disallow_blocks_and_failure_skips(self):
        cache = {}
        self.assertTrue(tipwatch.robots_allows("https://x.example/feed.xml", lambda u: (404, ""), cache, NOW))
        self.assertFalse(tipwatch.robots_allows("https://y.example/feed.xml", lambda u: (200, "User-agent: *\nDisallow: /feed"), {}, NOW))
        self.assertTrue(tipwatch.robots_allows("https://z.example/feed.xml", lambda u: (200, "User-agent: *\nDisallow: /private"), {}, NOW))
        self.assertFalse(tipwatch.robots_allows("https://w.example/feed.xml", lambda u: (500, ""), {}, NOW))
        self.assertFalse(tipwatch.robots_allows("https://v.example/feed.xml", lambda u: (0, ""), {}, NOW))

    def test_a_round_skips_a_feed_that_robots_blocks(self):
        feeds = [{"id": "a", "name": "A", "url": "https://a.example/rss"}]
        fetch = lambda u, headers=None: (200, "User-agent: *\nDisallow: /") if u.endswith("/robots.txt") else (200, read("tip-rss-a.xml"))
        st = {"items": [], "robots": {}}
        leads, status = tipwatch.run_round(st, feeds, NOW, fetch)
        self.assertFalse(status[0]["ok"])
        self.assertEqual(st["items"], [])


class Round(unittest.TestCase):
    def test_a_full_round_with_fake_feeds(self):
        feeds = [{"id": "a", "name": "A", "url": "https://a.example/rss"}, {"id": "b", "name": "B", "url": "https://b.example/atom"}]
        fetch = fake_fetch({"https://a.example/rss": read("tip-rss-a.xml"), "https://b.example/atom": read("tip-atom-b.xml")})
        leads, status = tipwatch.run_round({"items": [], "robots": {}}, feeds, NOW, fetch)
        self.assertTrue(all(s["ok"] for s in status))
        self.assertEqual(len(leads), 1)


class NeverPublished(unittest.TestCase):
    def test_tip_files_inside_the_repo_are_refused(self):
        with self.assertRaises(ValueError):
            tipwatch.refuse_published_path(os.path.join(ROOT, "data"))
        with self.assertRaises(ValueError):
            tipwatch.refuse_published_path(ROOT)
        self.assertEqual(tipwatch.refuse_published_path(tempfile.gettempdir()), tempfile.gettempdir())
        self.assertFalse(os.path.realpath(tipwatch.DEFAULT_DIR).startswith(ROOT))

    def test_main_refuses_a_repo_path(self):
        with self.assertRaises(ValueError):
            tipwatch.main(["--once", "--dir", os.path.join(ROOT, "data")])

    def test_no_tip_text_reaches_the_published_data(self):
        titles = [i["title"] for f in ("tip-rss-a.xml", "tip-atom-b.xml") for i in tipwatch.parse_feed(read(f), "x")]
        events, status = build_data.build(FX, NOW)
        blob = json.dumps(events) + json.dumps(status)
        for t in titles:
            self.assertNotIn(t, blob)
            self.assertNotIn(t.split(" - ")[0], blob)
        for link in ("https://a.example/ua", "https://b.example/ua"):
            self.assertNotIn(link, blob)

    def test_no_published_code_or_page_reads_the_tip_files(self):
        for name in ("tools/build_data.py", "tools/lib.py", "tools/probes.py", "tools/news_lane.py", "app.js", "lib.js", "index.html", "event.html", "tv.html", "sw.js"):
            src = open(os.path.join(ROOT, name), encoding="utf-8").read().lower()
            for bad in ("tipwatch", "tip-feed", "leads.json", "aviation-leads"):
                self.assertNotIn(bad, src, "%s mentions %s" % (name, bad))
        wf = open(os.path.join(ROOT, ".github", "workflows", "pages.yml"), encoding="utf-8").read().lower()
        self.assertNotIn("tipwatch", wf)

    def test_every_tip_feed_has_a_terms_record_and_is_not_a_published_source(self):
        for f in tipwatch.FEEDS:
            self.assertIn(f["id"], feed_terms.TIP_FEEDS)
        self.assertEqual({s["id"] for s in build_data.SOURCES} & set(feed_terms.TIP_FEEDS), set())

    def test_tipwatch_imports_no_cloud_model_client(self):
        src = open(os.path.join(ROOT, "tools", "tipwatch.py"), encoding="utf-8").read()
        imports = " ".join(re.findall(r"^\s*(?:import|from)\s+(\S+)", src, re.M)).lower()
        for bad in ("anthropic", "openai", "google", "genai", "claude", "gemini", "requests"):
            self.assertNotIn(bad, imports)


if __name__ == "__main__":
    unittest.main()
