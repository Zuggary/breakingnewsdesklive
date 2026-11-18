import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools import build_data, recurring
from tools.lib import iso_utc, parse_time

FIXTURES = Path(__file__).with_name("fixtures")
REPLAY = json.loads((FIXTURES / "replay-1118.json").read_text())
NOW = parse_time(REPLAY["generated"])


def closure(code="ZZZ", time=NOW, reason="Airport closed"):
    return {"id": "faa-closure-" + code, "source_id": "atd-faa",
            "title": "Airport closed at " + code, "time": iso_utc(time),
            "detail": {"reason": reason}}


class RoutineTests(unittest.TestCase):
    def test_history_counts_distinct_utc_days_and_expires(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "closure-days.json"
            path.write_text(json.dumps({"YYY": ["2026-11-05"]}))
            for offset in (6, 2, 2):
                day = NOW - timedelta(days=offset)
                event = closure(time=day)
                self.assertEqual(recurring.filter_closures([event], day, directory), ([event], []))

            event = closure()
            visible, dropped = recurring.filter_closures([event], NOW, directory)
            self.assertEqual(visible, [])
            self.assertEqual([row["id"] for row in dropped], [event["id"]])
            self.assertEqual(json.loads((path.parent / "routine.json").read_text()), dropped)
            self.assertEqual(json.loads(path.read_text()), {"ZZZ": ["2026-11-12", "2026-11-16", "2026-11-18"]})

            tomorrow = NOW + timedelta(days=1)
            self.assertEqual(recurring.filter_closures([event], tomorrow, directory), ([event], []))

    def test_unusual_closures_and_other_faa_events_stay_visible(self):
        for reason in ("Weather", "Aircraft accident", "Runway repairs", "Security",
                       "Unscheduled closure", "Multi-day closure", "Closed for 3 days"):
            with self.subTest(reason=reason):
                e = closure("SNA", reason=reason)
                self.assertEqual(recurring.filter_closures([e], NOW), ([e], []))
        events = [dict(closure("SNA"), title="Airport closed at SNA for runway repairs"),
                  dict(closure("SNA"), title="Ground stop at SNA"),
                  dict(closure("SNA"), source_id="example")]
        self.assertEqual(recurring.filter_closures(events, NOW), (events, []))

    def test_replay_keeps_sna_out_of_feed_and_stale_events_out_of_top_ten(self):
        events, dropped = recurring.filter_closures(REPLAY["events"], NOW)
        self.assertEqual([row["id"] for row in dropped], ["faa-closure-SNA"])
        ids = [e["id"] for e in sorted(events, key=lambda e: build_data.rank_key(e, NOW))]
        self.assertNotIn("faa-closure-SNA", ids)
        self.assertNotIn("usgs-us7000tymu", ids[:10])
        self.assertNotIn("volcano-311120", ids[:10])

    def test_rank_uses_update_time_and_preserves_extreme_priority(self):
        stale = {"type": "volcano", "severity": "severe", "score": 99, "big": True,
                 "time": iso_utc(NOW - timedelta(hours=24, seconds=1))}
        at_cutoff = iso_utc(NOW - timedelta(hours=24))
        moderate = dict(stale, time=at_cutoff, severity="moderate", source_id="nws-alerts")
        extreme = dict(stale, severity="extreme")
        updated = dict(stale, updated=at_cutoff)
        self.assertEqual(sorted([stale, moderate, extreme, updated], key=lambda e: build_data.rank_key(e, NOW)),
                         [extreme, updated, moderate, stale])

    def test_build_writes_routine_report_and_replaces_previous_closure(self):
        faa = next(src for src in build_data.SOURCES if src["id"] == "atd-faa")
        payload = {"updated_utc": iso_utc(NOW), "events": [{"kind": "closure", "code": "SNA"}]}
        with TemporaryDirectory() as directory:
            path = Path(directory)
            events_file = path / "events.json"
            events_file.write_text(json.dumps({"events": [closure("SNA")]}))
            with (patch.object(sys, "argv", ["build_data", "--out", directory, "--fixtures", directory]),
                  patch.object(build_data, "OUT_DIR", None),
                  patch.object(build_data, "datetime", wraps=build_data.datetime) as clock,
                  patch.object(build_data, "SOURCES", [faa]),
                  patch.object(build_data, "fetch_json", return_value=payload)):
                clock.now.return_value = NOW
                self.assertEqual(build_data.main(), 0)
            self.assertEqual(json.loads(events_file.read_text())["events"], [])
            self.assertEqual(json.loads((path / "closure-days.json").read_text()), {"SNA": ["2026-11-18"]})
            self.assertEqual(json.loads((path / "routine.json").read_text())[0]["id"], "faa-closure-SNA")


class ReviewFixes(unittest.TestCase):
    def test_extreme_or_emergency_sna_closure_still_shows_and_new_dir_is_made(self):
        import tempfile
        from datetime import datetime, timezone
        from tools import recurring
        now = datetime(2026, 11, 18, 20, tzinfo=timezone.utc)
        base = {"id": "x", "source_id": "atd-faa", "title": "Airport closed at SNA", "time": "2026-11-18T19:00:00Z", "severity": "severe"}
        extreme = dict(base, id="y", severity="extreme")
        emergency = dict(base, id="z", title="Airport closed at SNA after an emergency landing")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "new" / "dir"  # does not exist yet
            visible, dropped = recurring.filter_closures([base, extreme, emergency], now, out)
            self.assertEqual([e["id"] for e in visible], ["y", "z"])
            self.assertEqual([x["id"] for x in dropped], ["x"])
