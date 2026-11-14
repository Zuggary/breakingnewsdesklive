import json, os, sys, unittest
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import build_data, lib

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.status = build_data.build(FIX, NOW)

    def test_sources_ok(self):
        self.assertTrue(all(s["ok"] for s in self.status), self.status)

    def test_fields(self):
        self.assertGreaterEqual(len(self.events), 4)
        for e in self.events:
            for k in ("id", "type", "title", "time", "source", "source_url", "score", "summary", "region"):
                self.assertTrue(e.get(k) is not None, (k, e["id"]))
            self.assertTrue(e["source_url"].startswith("https://"))
            self.assertTrue(e["time"].endswith("Z"))

    def test_sorted(self):
        sc = [e["score"] for e in self.events]
        self.assertEqual(sc, sorted(sc, reverse=True))

    def test_summaries_pass_guard(self):
        for e in self.events:
            self.assertTrue(lib.guard_ok(e["summary"], e), e["summary"])

    def test_guard_rejects_invented_number(self):
        e = next(x for x in self.events if x["type"] == "earthquake")
        self.assertFalse(lib.guard_ok("A magnitude 9.9 earthquake struck.", e))

    def test_guard_rejects_invented_place(self):
        e = next(x for x in self.events if x["type"] == "earthquake")
        self.assertFalse(lib.guard_ok("An earthquake hit Atlantis.", e))

    def test_old_events_dropped(self):
        for e in self.events:
            self.assertLessEqual((NOW - lib.parse_time(e["time"])).total_seconds(), 168 * 3600)

    def test_one_bad_source_does_not_stop_build(self):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        for f in os.listdir(FIX):
            shutil.copy(os.path.join(FIX, f), d)
        open(os.path.join(d, "eonet.json"), "w").write("not json")
        ev, st = build_data.build(d, NOW)
        self.assertFalse(next(s for s in st if s["id"] == "eonet")["ok"])
        self.assertTrue(ev)

    def test_no_ads_or_trackers_in_pages(self):
        root = os.path.dirname(FIX.rstrip("/")); root = os.path.dirname(root)
        for p in ("index.html", "about.html", "privacy.html"):
            t = open(os.path.join(root, p)).read().lower()
            for bad in ("adsbygoogle", "googletagmanager", "google-analytics", "gtag(", "@gmail"):
                self.assertNotIn(bad, t, (p, bad))


if __name__ == "__main__":
    unittest.main()
