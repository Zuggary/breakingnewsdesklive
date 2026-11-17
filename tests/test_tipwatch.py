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
    def test_feed_freshness_uses_newest_item_and_drops_expired_items(self):
        feed = {"id": "example", "url": "https://news.example/rss"}
        for hours, stale in ((24, False), (25, True), (49, True)):
            with self.subTest(hours=hours):
                rows = []
                for i, age in enumerate((72, hours)):
                    rows.append("<item><title>Made up library news</title>"
                                "<link>https://news.example/%d</link><pubDate>%s</pubDate></item>"
                                % (i, tipwatch.iso(NOW - timedelta(hours=age))))
                body = "<rss><channel>%s</channel></rss>" % "".join(rows)
                store = {"items": [], "robots": {}}
                _, status = tipwatch.run_round(store, [feed], NOW,
                                              fake_fetch({feed["url"]: body}))
                self.assertEqual(status[0]["ok"], not stale)
                self.assertEqual(status[0].get("stale", False), stale)
                if stale:
                    self.assertEqual(status[0]["error"],
                                     "stale feed (newest item %d h old)" % hours)
                self.assertEqual(len(store["items"]), int(hours <= 48))

    def test_cnn_uses_gdelt_instead_of_stale_rss(self):
        self.assertFalse(any("rss.cnn.com" in f["url"] for f in tipwatch.FEEDS))
        self.assertFalse(any(f["id"] == "cnn" for f in tipwatch.FEEDS))
        self.assertIn("GDELT", feed_terms.TIP_FEEDS["cnn"]["note"])
        self.assertIn("stale", feed_terms.TIP_FEEDS["cnn"]["note"])
        self.assertFalse(feed_terms.TIP_FEEDS["cnn"]["terms_read"])

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


class SecurityLane(unittest.TestCase):
    def leads(self):
        st = {"items": [], "robots": {}}
        items = [
            {"feed": "cnn", "title": "US intelligence: Iran weighing dirty bomb or chemical attack on officials in Washington", "link": "https://c.example/1", "time": "2026-11-16T23:30:00Z"},
            {"feed": "guardian", "title": "Iran weighing dirty bomb or chemical attack on US officials in Washington, report says", "link": "https://g.example/1", "time": "2026-11-16T23:50:00Z"},
            {"feed": "nbc", "title": "White House says no credible threats after report Iran weighing dirty bomb attack on officials in Washington", "link": "https://n.example/1", "time": "2026-11-17T00:10:00Z"},
            {"feed": "bbc", "title": "Storm hits coast", "link": "https://b.example/1", "time": "2026-11-17T00:00:00Z"}]
        tipwatch.add_items(st, items, datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc))
        return tipwatch.build_leads(st, datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc))

    def test_a_security_story_from_2_or_more_outlets_becomes_a_candidate(self):
        leads = self.leads()
        self.assertEqual(leads[0]["topic"], "security")
        cands = tipwatch.security_candidates(leads)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["n_outlets"], 3)
        self.assertTrue(cands[0]["official_response_found"])
        self.assertIn("White House says", cands[0]["response_hints"][0])

    def test_a_candidate_never_publishes_itself_and_lists_what_is_missing(self):
        c = tipwatch.security_candidates(self.leads())[0]
        self.assertIn("Never automatic", c["publish"])
        self.assertTrue(any("official response line" in n for n in c["needs"]))
        self.assertTrue(any("DC not Washington State" in n for n in c["needs"]))

    def test_non_security_leads_are_not_candidates(self):
        st = {"items": [], "robots": {}}
        now = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)
        tipwatch.add_items(st, [{"feed": "a", "title": "Council approves new library budget plan", "link": "https://a.example/1", "time": "2026-11-17T00:00:00Z"},
                                {"feed": "b", "title": "Library budget plan approved by council vote", "link": "https://b.example/1", "time": "2026-11-17T00:05:00Z"}], now)
        self.assertEqual(tipwatch.security_candidates(tipwatch.build_leads(st, now)), [])

    def test_security_terms_tag_the_topic(self):
        for t in ("Explosion reported near stadium", "Cyberattack hits hospital network", "Evacuation ordered after threat", "Ground stop at airport after alarm"):
            self.assertEqual(tipwatch.tag_topic(t), "security", t)
        self.assertEqual(tipwatch.tag_topic("United Airlines outage grounds flights"), "aviation")


class GdeltSecurity(unittest.TestCase):
    def gkg(self, rows):
        import io
        import zipfile
        lines = []
        for date, domain, url, title in rows:
            f = [""] * 27
            f[1], f[3], f[4], f[26] = date, domain, url, "<PAGE_TITLE>%s</PAGE_TITLE>" % title
            lines.append("\t".join(f))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("x.gkg.csv", "\n".join(lines))
        return buf.getvalue()

    def test_only_security_titles_are_kept(self):
        z = self.gkg([("20261117003000", "www.dailymail.com", "https://dailymail.example/1", "Iran weighing dirty bomb attack on US officials, report says"),
                      ("20261117003000", "bakery.example", "https://bakery.example/1", "Local bakery wins award")])
        items = tipwatch.read_gkg_security(z)
        self.assertEqual([i["feed"] for i in items], ["dailymail.com"])
        self.assertEqual(items[0]["time"], "2026-11-17T00:30:00Z")
        self.assertEqual(set(items[0]), {"feed", "title", "link", "time"})

    def test_cnn_non_security_titles_reach_store_with_cnn_feed_id(self):
        rows = [("20261117003000", domain, "https://news.example/%d" % i,
                 "Made up library opens new reading room")
                for i, domain in enumerate(("cnn.com", "edition.cnn.com", "www.cnn.com"))]
        z = self.gkg(rows)
        fetch = lambda url: (b"x https://data.gdeltproject.org/gdeltv2/20261117003000.gkg.csv.zip"
                             if url.endswith("lastupdate.txt") else z)
        store = {"items": [], "robots": {}}
        tipwatch.run_round(store, [], datetime(2026, 11, 17, 1, tzinfo=timezone.utc),
                          gdelt_bytes=fetch)
        self.assertEqual([i["feed"] for i in store["items"]], ["cnn"] * 3)
        self.assertEqual(store["items"][0]["title"], rows[0][3])
        self.assertEqual(store["items"][0]["time"], "2026-11-17T00:30:00Z")

    def test_cnn_limit_is_per_file_and_does_not_limit_other_security_titles(self):
        rows = [("20261117003000", "cnn.com", "https://news.example/%d" % i,
                 "Made up library opens reading room") for i in range(61)]
        rows.append(("20261117003000", "other.example", "https://other.example/1",
                     "Explosion reported near fictional stadium"))
        items = tipwatch.read_gkg_security(self.gkg(rows))
        self.assertEqual([i["feed"] for i in items], ["cnn"] * 60 + ["other.example"])
        self.assertTrue(all(set(i) == {"feed", "title", "link", "time"} for i in items))

    def test_a_gkg_file_is_read_once(self):
        z = self.gkg([("20261117003000", "a.example", "https://a.example/1", "Explosion reported near stadium")])
        calls = []
        def fetch(url):
            calls.append(url)
            return b"x http://data.gdeltproject.org/gdeltv2/20261117003000.gkg.csv.zip" if url.endswith("lastupdate.txt") else z
        st = {"items": [], "robots": {}}
        a = tipwatch.gdelt_security_items(st, fetch, NOW)
        b = tipwatch.gdelt_security_items(st, fetch, NOW)
        self.assertEqual((len(a), len(b)), (1, 0))

    def test_candidates_count_distinct_headlines_so_syndicated_copies_are_one(self):
        st = {"items": [], "robots": {}}
        now = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)
        same = "Iran threats prompt US officials to shelter on bases"
        items = [{"feed": "st%d.example" % i, "title": same, "link": "https://st%d.example/x" % i, "time": "2026-11-17T00:10:00Z"} for i in range(4)]
        items.append({"feed": "other.example", "title": "US officials shelter on bases after Iran threats, report says", "link": "https://other.example/x", "time": "2026-11-17T00:20:00Z"})
        tipwatch.add_items(st, items, now)
        c = tipwatch.security_candidates(tipwatch.build_leads(st, now))
        self.assertEqual(c[0]["n_outlets"], 5)
        self.assertEqual(c[0]["distinct_headlines"], 2)

    def test_a_round_can_include_gdelt_and_it_stays_internal(self):
        z = self.gkg([("20261117003000", "cnn.com", "https://news.example/1", "Explosion reported near stadium"),
                      ("20261117003000", "b.example", "https://b.example/1", "Explosion near stadium reported by police")])
        fetch = lambda url: (b"x https://data.gdeltproject.org/gdeltv2/20261117003000.gkg.csv.zip" if url.endswith("lastupdate.txt") else z)
        st = {"items": [], "robots": {}}
        leads, status = tipwatch.run_round(st, [], datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc), gdelt_bytes=fetch)
        self.assertTrue(status[-1]["ok"])
        self.assertEqual(status[-1]["id"], "gdelt-security")
        candidates = tipwatch.security_candidates(leads)
        self.assertEqual(len(candidates), 1)
        self.assertIn("cnn", candidates[0]["outlets"])
        self.assertIn("cnn", tipwatch.auto_news.TOP_OUTLETS)


class Alerts(unittest.TestCase):
    def cand(self, n, heads, lead="lead-1"):
        return {"lead": lead, "n_outlets": n, "distinct_headlines": heads, "first_seen": "2026-11-17T16:15:00Z", "official_response_found": False,
                "items": [{"title": "NSA classified network goes down, reports say"}]}

    def test_a_widely_carried_security_story_raises_an_internal_alert_once(self):
        seen = set()
        self.assertEqual(len(tipwatch.alerts_for([self.cand(8, 5)], seen)), 1)
        self.assertEqual(tipwatch.alerts_for([self.cand(8, 5)], seen), [])

    def test_small_or_copied_stories_do_not(self):
        self.assertEqual(tipwatch.alerts_for([self.cand(3, 3)], set()), [])
        self.assertEqual(tipwatch.alerts_for([self.cand(30, 1)], set()), [])
