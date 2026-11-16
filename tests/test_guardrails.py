"""GD6 phase 1 guardrails: feed gate, claim words, status labels, kill switch, identity label."""
import json, os, sys, unittest
from datetime import date
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import build_data, feed_terms  # noqa: E402


class FeedGate(unittest.TestCase):
    def test_every_source_has_a_record(self):
        missing = [s["id"] for s in build_data.SOURCES if s["id"] not in feed_terms.FEED_TERMS]
        self.assertEqual(missing, [])

    def test_every_source_passes_today(self):
        for s in build_data.SOURCES:
            ok, why = feed_terms.gate(s)
            self.assertTrue(ok, "%s: %s" % (s["id"], why))

    def test_unrecorded_feed_is_refused(self):
        self.assertEqual(feed_terms.gate({"id": "some-new-feed"}), (False, "no terms record"))

    def test_commercial_no_is_refused(self):
        feed_terms.FEED_TERMS["x-test"] = {"commercial": "no", "checked": "2026-11-16"}
        try:
            self.assertFalse(feed_terms.gate({"id": "x-test"})[0])
        finally:
            del feed_terms.FEED_TERMS["x-test"]

    def test_old_record_is_refused(self):
        s = build_data.SOURCES[0]
        ok, why = feed_terms.gate(s, today=date(2028, 1, 1))
        self.assertFalse(ok)
        self.assertIn("days old", why)

    def test_blocked_feed_is_skipped_by_the_job(self):
        saved = feed_terms.FEED_TERMS.pop("usgs-quakes")
        try:
            events, status = build_data.build(os.path.join(ROOT, "tests", "fixtures"))
            rec = next(s for s in status if s["id"] == "usgs-quakes")
            self.assertFalse(rec["ok"])
            self.assertIn("feed gate", rec["error"])
        finally:
            feed_terms.FEED_TERMS["usgs-quakes"] = saved

    def test_ads_blockers_listed(self):
        b = feed_terms.ads_blockers(build_data.SOURCES)
        for must in ("ms365", "gdacs", "status-github"):
            self.assertIn(must, b)
        self.assertNotIn("usgs-quakes", b)


if __name__ == "__main__":
    unittest.main()


class ClaimsAndStatus(unittest.TestCase):
    def test_blocked_words(self):
        from tools import lib
        for bad in ("Police arrested a suspect.", "Three people were killed.", "The victims were", "He was blamed for it"):
            self.assertFalse(lib.claims_ok(bad), bad)
        for good in ("A magnitude 5.0 earthquake was recorded.", "FAA status for San Diego (SAN): airport closed."):
            self.assertTrue(lib.claims_ok(good), good)

    def test_safe_summary_passes_the_fact_gate(self):
        from tools import lib
        ev = {"title": "x", "place": "y", "type": "recall", "detail": {}}
        self.assertTrue(lib.guard_ok(lib.SAFE_SUMMARY, ev), lib.SAFE_SUMMARY)

    def test_status_labels(self):
        from datetime import datetime, timezone, timedelta
        from tools import lib
        now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
        iso = lambda m: (now - timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(lib.status_label({"type": "headline", "time": iso(500)}, now), "UNVERIFIED")
        self.assertEqual(lib.status_label({"type": "statement", "time": iso(5)}, now), "UNVERIFIED")
        self.assertEqual(lib.status_label({"type": "earthquake", "time": iso(30)}, now), "DEVELOPING")
        self.assertEqual(lib.status_label({"type": "earthquake", "time": iso(300)}, now), "")

    def test_built_events_carry_a_status_and_clean_summaries(self):
        events, _ = build_data.build(os.path.join(ROOT, "tests", "fixtures"))
        from tools import lib
        self.assertTrue(events)
        for e in events:
            self.assertIn("status", e)
            self.assertTrue(lib.claims_ok(e["summary"]), e["summary"])
