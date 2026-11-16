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


class KillSwitch(unittest.TestCase):
    def ev(self, i, t, title):
        return {"id": i, "type": t, "title": title, "place": "Somewhere", "source": "s"}

    def test_crisis_headline_is_held(self):
        from tools import killswitch
        evs = [self.ev("a", "headline", "Headline: “Plane crash kills 40 near airport”"), self.ev("b", "headline", "Headline: “Budget talks resume”")]
        out, held = killswitch.apply(evs, set())
        self.assertEqual([e["id"] for e in out], ["b"])
        self.assertEqual(held[0]["id"], "a")

    def test_person_approval_clears_a_hold(self):
        from tools import killswitch
        evs = [self.ev("a", "headline", "Headline: “Shooting at stadium”")]
        out, held = killswitch.apply(evs, {"a"})
        self.assertEqual((len(out), len(held)), (1, 0))

    def test_official_hazard_titles_are_not_held(self):
        from tools import killswitch
        evs = [self.ev("q", "earthquake", "M 5.5 earthquake"), self.ev("w", "weather", "Flood Warning"), self.ev("t", "transport", "Airport closed at SAN"), self.ev("r", "recall", "CPSC recall: Rugs due to risk of injury or death from fire")]
        out, held = killswitch.apply(evs, set())
        self.assertEqual((len(out), len(held)), (4, 0))

    def test_global_stop_by_env_and_file(self):
        import tempfile
        from tools import killswitch
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(killswitch.global_stop(d))
            open(os.path.join(d, "KILL"), "w").close()
            self.assertTrue(killswitch.global_stop(d))
        os.environ["BND_KILL"] = "1"
        try:
            self.assertTrue(killswitch.global_stop("/nonexistent"))
        finally:
            del os.environ["BND_KILL"]

    def test_job_writes_nothing_when_killed(self):
        import tempfile
        os.environ["BND_KILL"] = "1"
        old = sys.argv
        try:
            with tempfile.TemporaryDirectory() as d:
                sys.argv = ["build_data.py", "--out", d, "--fixtures", os.path.join(ROOT, "tests", "fixtures")]
                self.assertEqual(build_data.main(), 0)
                self.assertEqual(os.listdir(d), [])
        finally:
            sys.argv = old
            del os.environ["BND_KILL"]

    def test_job_writes_held_file_and_keeps_held_out(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            old = sys.argv
            sys.argv = ["build_data.py", "--out", d, "--fixtures", os.path.join(ROOT, "tests", "fixtures")]
            try:
                build_data.main()
            finally:
                sys.argv = old
            held = json.load(open(os.path.join(d, "held.json")))
            ids = {e["id"] for e in json.load(open(os.path.join(d, "events.json")))["events"]}
            self.assertEqual(held["count"], len(held["items"]))
            self.assertTrue(all(h["id"] not in ids for h in held["items"]))

    def test_approved_file_is_a_list(self):
        data = json.load(open(os.path.join(ROOT, "approved.json")))
        self.assertIsInstance(data, list)


class IdentityLabel(unittest.TestCase):
    def test_every_page_has_the_label(self):
        pages = [f for f in os.listdir(ROOT) if f.endswith(".html")]
        self.assertGreaterEqual(len(pages), 7)
        for p in pages:
            self.assertIn("AI-ASSISTED WIRE DESK", open(os.path.join(ROOT, p), encoding="utf-8").read(), p)

    def test_non_affiliation_line_on_reading_pages(self):
        for p in ("index.html", "event.html", "about.html", "privacy.html", "data.html", "corrections.html"):
            self.assertIn("No agency is affiliated", open(os.path.join(ROOT, p), encoding="utf-8").read(), p)


class Masthead(unittest.TestCase):
    def test_about_has_masthead_and_contact(self):
        t = open(os.path.join(ROOT, "about.html"), encoding="utf-8").read()
        for need in ("Masthead", "contact@breakingnewsdesklive.com", "UNVERIFIED", "crisis switch", "Illustration"):
            self.assertIn(need, t)

    def test_corrections_page_has_process(self):
        t = open(os.path.join(ROOT, "corrections.html"), encoding="utf-8").read()
        for need in ("Report an error", "What we do", "Past corrections"):
            self.assertIn(need, t)


class Gd8Part2(unittest.TestCase):
    def test_awc_keeps_ash_and_cyclone_only_and_latest_wins(self):
        from tools import build_data
        src = next(s for s in build_data.SOURCES if s["id"] == "awc-sigmet")
        ev = build_data.parse_awc(json.load(open(os.path.join(ROOT, "tests", "fixtures", "awc-sigmet.json"))), src)
        self.assertEqual(sorted(e["id"] for e in ev), ["awc-VHHK-3-tc", "awc-WAAF-14-va"])
        va = next(e for e in ev if e["id"].endswith("-va"))
        self.assertEqual(va["detail"]["top_ft"], 18000)          # the later report of series 14
        self.assertEqual(va["type"], "aviation")
        self.assertEqual(va["severity"], "severe")
        self.assertTrue(va["source_url"].startswith("https://"))

    def test_awc_has_a_terms_record_and_a_credit(self):
        from tools import feed_terms
        self.assertEqual(feed_terms.FEED_TERMS["awc-sigmet"]["commercial"], "yes")
        src = next(s for s in build_data.SOURCES if s["id"] == "awc-sigmet")
        self.assertIn("not flight cancellations", src["licence"])

    def test_aviation_summary_says_advisory_not_cancellation(self):
        events, _ = build_data.build(os.path.join(ROOT, "tests", "fixtures"), __import__("datetime").datetime(2026, 11, 14, 12, 0, tzinfo=__import__("datetime").timezone.utc))
        av = [e for e in events if e["type"] == "aviation"]
        self.assertTrue(av)
        for e in av:
            self.assertIn("not a flight cancellation", e["summary"])

    def test_sec_parser_keeps_8k_only_and_is_not_live(self):
        from tools import sec_edgar
        items = sec_edgar.parse_atom(open(os.path.join(ROOT, "tests", "fixtures", "sec-8k.xml"), encoding="utf-8").read())
        self.assertEqual([i["company"] for i in items], ["Example Corp", "Sample Holdings Inc"])
        self.assertEqual(items[0]["filed"], "2026-11-17T01:40:00Z")
        self.assertNotIn("sec-8k", {s["id"] for s in build_data.SOURCES})
        self.assertIn("contact@breakingnewsdesklive.com", sec_edgar.UA)
        self.assertNotIn("@gmail", sec_edgar.UA)
