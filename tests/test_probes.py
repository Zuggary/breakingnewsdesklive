"""GD7 part A: probes. Fake fetch and a simulated clock, plus one test against a real local server that returns 503."""
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import probes, probe_runner  # noqa: E402

T0 = datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc)   # 9:00 AM ET


def svc(i, group="bank", name=None):
    return {"id": i, "name": name or i.title(), "group": group, "login_url": "http://x/%s" % i, "check_word": "Hello"}


def fetch_ok(url, timeout):
    return 200, "<html>Hello</html>", 120


def fetch_503(url, timeout):
    return 503, "Service unavailable", 90


def fetch_timeout(url, timeout):
    raise TimeoutError("timed out")


def step(state, services, minutes, fetch, last):
    now = T0 + timedelta(minutes=minutes)
    probes.run_cycle(state, services, now, fetch, last)
    return now


class ProbeList(unittest.TestCase):
    def test_list_has_30_services_with_url_and_word(self):
        lst = json.load(open(os.path.join(ROOT, "tools", "probe_list.json")))
        self.assertEqual(len(lst), 30)
        self.assertEqual(len({s["id"] for s in lst}), 30)
        for s in lst:
            self.assertTrue(s["login_url"].startswith("https://"), s["id"])
            self.assertTrue(s["check_word"], s["id"])
        groups = {s["group"] for s in lst}
        self.assertEqual(groups, {"bank", "payment app", "card issuer", "carrier", "airline"})
        for need in ("zelle", "venmo", "paypal", "cashapp", "chase", "bofa", "wellsfargo", "usbank"):
            self.assertIn(need, {s["id"] for s in lst})
        self.assertEqual(sum(1 for s in lst if s["group"] == "carrier"), 4)
        self.assertEqual(sum(1 for s in lst if s["group"] == "airline"), 4)


class Detection(unittest.TestCase):
    def test_503_produces_an_item_within_10_minutes_and_clears_after_3_healthy(self):
        services, state, last = [svc("chase")], {}, {}
        step(state, services, 0, fetch_503, last)      # onset: first failing probe
        step(state, services, 3, fetch_503, last)
        now = step(state, services, 6, fetch_503, last)
        snap = probes.snapshot(state, services, now)
        ev = probes.events_from_snapshot(snap, now)
        self.assertEqual(len(ev), 1)
        self.assertEqual(snap["services"][0]["status"], "down")
        self.assertLessEqual((now - T0).total_seconds(), 600)
        self.assertEqual(ev[0]["title"], "Chase login page returning errors")
        self.assertIn("9:00 AM ET", ev[0]["summary_override"])
        # Two healthy probes are not enough. Three clear it.
        step(state, services, 9, fetch_ok, last)
        now = step(state, services, 12, fetch_ok, last)
        self.assertEqual(probes.snapshot(state, services, now)["services"][0]["status"], "down")
        now = step(state, services, 15, fetch_ok, last)
        snap = probes.snapshot(state, services, now)
        self.assertEqual(snap["services"][0]["status"], "up")
        ev = probes.events_from_snapshot(snap, now)
        self.assertEqual([e["title"] for e in ev], ["Chase login page: errors cleared"])
        self.assertEqual(ev[0]["severity"], "minor")
        self.assertEqual(len(snap["incidents"]), 1)

    def test_timeout_counts_as_down(self):
        services, state, last = [svc("chase")], {}, {}
        for m in (0, 3, 6):
            now = step(state, services, m, fetch_timeout, last)
        self.assertEqual(probes.snapshot(state, services, now)["services"][0]["status"], "down")

    def test_two_failures_are_not_enough(self):
        services, state, last = [svc("chase")], {}, {}
        step(state, services, 0, fetch_503, last)
        now = step(state, services, 3, fetch_503, last)
        self.assertEqual(probes.snapshot(state, services, now)["services"][0]["status"], "up")
        self.assertEqual(probes.events_from_snapshot(probes.snapshot(state, services, now), now), [])

    def test_missing_check_word_three_times_is_degraded(self):
        services, state, last = [svc("chase")], {}, {}
        nowords = lambda u, t: (200, "<html>Maintenance</html>", 100)
        for m in (0, 3, 6):
            now = step(state, services, m, nowords, last)
        self.assertEqual(probes.snapshot(state, services, now)["services"][0]["status"], "degraded")
        ev = probes.events_from_snapshot(probes.snapshot(state, services, now), now)
        self.assertEqual(ev[0]["title"], "Chase login page responding badly")
        self.assertEqual(ev[0]["severity"], "moderate")

    def test_three_times_the_median_is_degraded(self):
        services, state, last = [svc("chase")], {}, {}
        for m in range(0, 21 * 3, 3):
            step(state, services, m, fetch_ok, last)    # 21 healthy probes at 120 ms
        slow = lambda u, t: (200, "<html>Hello</html>", 500)
        base = 21 * 3
        for m in (base, base + 3, base + 6):
            now = step(state, services, m, slow, last)
        self.assertEqual(probes.snapshot(state, services, now)["services"][0]["status"], "degraded")

    def test_blocked_service_is_unprobeable_and_never_an_item(self):
        services, state, last = [svc("tmobile", "carrier")], {}, {}
        blocked = lambda u, t: (403, "", 80)
        for m in (0, 3, 6, 9):
            now = step(state, services, m, blocked, last)
        snap = probes.snapshot(state, services, now)
        self.assertEqual(snap["services"][0]["status"], "unprobeable")
        self.assertEqual(probes.events_from_snapshot(snap, now), [])


class Grouping(unittest.TestCase):
    def test_four_banks_failing_together_make_one_big_item(self):
        names = ["chase", "bofa", "wellsfargo", "usbank"]
        services = [svc(n, "bank", {"chase": "Chase", "bofa": "Bank of America", "wellsfargo": "Wells Fargo", "usbank": "U.S. Bank"}[n]) for n in names]
        services.append(svc("delta", "airline", "Delta Air Lines"))
        state, last = {}, {}
        def f(url, timeout):
            return (503, "", 80) if url.rsplit("/", 1)[1] in names else (200, "Hello", 100)
        for m in (0, 3, 6):
            now = step(state, services, m, f, last)
        ev = probes.events_from_snapshot(probes.snapshot(state, services, now), now)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["title"], "4 bank login pages returning errors")
        self.assertTrue(ev[0]["big"])
        self.assertEqual(ev[0]["severity"], "severe")
        self.assertEqual(ev[0]["detail"]["services_failing"], 4)

    def test_failures_far_apart_are_separate_items(self):
        a, b = svc("chase"), svc("bofa", name="Bank of America")
        state, last = {}, {}
        fa = lambda u, t: (503, "", 80) if u.endswith("chase") else (200, "Hello", 100)
        for m in (0, 3, 6):
            step(state, [a, b], m, fa, last)
        fb = lambda u, t: (503, "", 80)
        for m in (9 + 30, 12 + 30, 15 + 30):   # bofa trouble begins 39 minutes later
            now = step(state, [a, b], m, fb, last)
        ev = [e for e in probes.events_from_snapshot(probes.snapshot(state, [a, b], now), now) if e["severity"] != "minor"]
        self.assertEqual(len(ev), 2)

    def test_mixed_groups_title(self):
        services = [svc("chase", "bank", "Chase"), svc("venmo", "payment app", "Venmo"), svc("att", "carrier", "AT&T")]
        state, last = {}, {}
        for m in (0, 3, 6):
            now = step(state, services, m, fetch_503, last)
        ev = probes.events_from_snapshot(probes.snapshot(state, services, now), now)
        self.assertEqual(ev[0]["title"], "3 service login pages returning errors")


class Spacing(unittest.TestCase):
    def test_no_service_is_probed_more_often_than_every_3_minutes(self):
        services = [svc("a"), svc("b")]
        state, last, log = {}, {}, []
        for sec in range(0, 3600, 20):            # the loop ticks every 20 seconds
            now = T0 + timedelta(seconds=sec)
            for sid, res in probes.run_cycle(state, services, now, fetch_ok, last):
                log.append((sid, now))
        for sid in ("a", "b"):
            ts = [t for s, t in log if s == sid]
            gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
            self.assertGreaterEqual(min(gaps), 180)
            self.assertEqual(len(ts), 20)

    def test_runner_logs_have_the_same_rule(self):
        self.assertEqual(probes.INTERVAL_S, 180)
        self.assertEqual(probes.TIMEOUT_S, 15)


class Stale(unittest.TestCase):
    def test_a_stale_snapshot_makes_no_items(self):
        services, state, last = [svc("chase")], {}, {}
        for m in (0, 3, 6):
            now = step(state, services, m, fetch_503, last)
        snap = probes.snapshot(state, services, now)
        self.assertEqual(len(probes.events_from_snapshot(snap, now)), 1)
        self.assertEqual(probes.events_from_snapshot(snap, now + timedelta(minutes=45)), [])


class NoModelCalls(unittest.TestCase):
    def test_probe_code_imports_no_model_client(self):
        for f in ("probes.py", "probe_runner.py"):
            src = open(os.path.join(ROOT, "tools", f), encoding="utf-8").read()
            imports = " ".join(re.findall(r"^\s*(?:import|from)\s+(\S+)", src, re.M)).lower()
            for bad in ("anthropic", "openai", "google", "genai", "claude", "gemini", "subprocess", "requests"):
                self.assertNotIn(bad, imports, "%s imports %s" % (f, bad))

    def test_probe_code_sends_no_credentials_or_posts(self):
        src = open(os.path.join(ROOT, "tools", "probes.py"), encoding="utf-8").read()
        self.assertIn('method="GET"', src)
        for bad in ("Authorization", "Cookie", "data=", "POST"):
            self.assertNotIn(bad, src.replace("Cookie, ", "").replace("post, ", ""))


class EndToEnd(unittest.TestCase):
    """A real local server that returns 503, probed through the runner."""

    def test_runner_against_a_503_server(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(503); self.end_headers(); self.wfile.write(b"down")
            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                lst = os.path.join(d, "list.json")
                json.dump([{"id": "testsvc", "name": "Test Service", "group": "bank", "login_url": "http://127.0.0.1:%d/" % srv.server_port, "check_word": "Hello"}], open(lst, "w"))
                old = probes.INTERVAL_S
                probes.INTERVAL_S = 0
                try:
                    for _ in range(3):
                        self.assertEqual(probe_runner.main(["--once", "--state", os.path.join(d, "s.json"), "--out", os.path.join(d, "p.json"), "--list", lst, "--log", os.path.join(d, "log.jsonl"), "--spacing", "0"]), 0)
                finally:
                    probes.INTERVAL_S = old
                snap = json.load(open(os.path.join(d, "p.json")))
                self.assertEqual(snap["services"][0]["status"], "down")
                ev = probes.events_from_snapshot(snap, datetime.now(timezone.utc))
                self.assertEqual(ev[0]["title"], "Test Service login page returning errors")
                self.assertEqual(len(open(os.path.join(d, "log.jsonl")).read().strip().split("\n")), 3)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()


class TopHeadline(unittest.TestCase):
    """A grouped outage of 3 or more services takes the top slot of the built data, which feeds the home page and the stream."""

    def test_big_probe_group_is_first_in_the_built_events(self):
        from tools import build_data
        events, status = build_data.build(os.path.join(ROOT, "tests", "fixtures"), datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
        self.assertTrue(events[0].get("big"), events[0]["title"])
        self.assertEqual(events[0]["title"], "4 bank login pages returning errors")
        self.assertEqual(events[0]["source"], "Desk probes (our own)")
        rec = next(s for s in status if s["id"] == "probes")
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["services_unprobeable"], 1)

    def test_home_page_and_stream_use_the_first_event(self):
        app = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
        tv = open(os.path.join(ROOT, "tv.html"), encoding="utf-8").read()
        self.assertIn("e.big", app)
        self.assertIn("TOP HEADLINE", app)
        self.assertIn("e.big", tv)
        self.assertIn("function top(){return S.ev.slice(0,8)}", tv)
        self.assertIn("e.type!=='statement'&&e.type!=='headline'", tv)   # outage items are kept on the stream

    def test_summary_passes_the_fact_gate(self):
        from tools import build_data, lib
        events, _ = build_data.build(os.path.join(ROOT, "tests", "fixtures"), datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
        for e in events:
            if e.get("source_id") == "probes":
                self.assertTrue(lib.guard_ok(e["summary"], e), e["summary"])
                self.assertTrue(lib.claims_ok(e["summary"]))
