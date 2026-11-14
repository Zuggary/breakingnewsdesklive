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

    def test_kp_storm_event(self):
        src = next(s for s in build_data.SOURCES if s["id"] == "swpc-kp")
        rows = [{"time_tag": "2026-11-14T06:00:00", "Kp": 6.33}, {"time_tag": "2026-11-14T03:00:00", "Kp": 2.0}]
        ev = build_data.parse_kp(rows, src)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["detail"]["g_scale"], 2)
        ev[0]["summary"] = lib.summarize(ev[0])
        self.assertTrue(lib.guard_ok(ev[0]["summary"], ev[0]), ev[0]["summary"])
        self.assertEqual(build_data.parse_kp([{"time_tag": "2026-11-14T06:00:00", "Kp": 3.0}], src), [])

    def test_first_seen_and_log(self):
        import tempfile
        d = tempfile.mkdtemp()
        evs = [dict(e) for e in self.events]
        self.assertEqual(build_data.track_seen(evs, d, NOW), [])
        self.assertEqual(evs[0]["first_seen"], evs[0]["time"])
        evs2 = [dict(e) for e in self.events] + [dict(self.events[0], id="new-1")]
        new = build_data.track_seen(evs2, d, NOW)
        self.assertEqual(new, ["new-1"])
        self.assertEqual(evs2[-1]["first_seen"], lib.iso_utc(NOW))
        self.assertEqual(len(open(os.path.join(d, "log.jsonl")).read().splitlines()), 2)

    def test_tsunami_warning_parsed_information_skipped(self):
        src = next(s for s in build_data.SOURCES if s["id"] == "tsunami-ak")
        xml = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:x:1</id><title>Tsunami Warning Number 2</title>'
               '<updated>2026-11-14T10:00:00Z</updated></entry><entry><id>urn:x:2</id><title>Tsunami Information Statement 1</title>'
               '<updated>2026-11-14T10:00:00Z</updated></entry></feed>')
        ev = build_data.parse_tsunami(xml, src)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["severity"], "extreme")
        ev[0]["summary"] = lib.summarize(ev[0])
        self.assertTrue(lib.guard_ok(ev[0]["summary"], ev[0]), ev[0]["summary"])

    def test_spc_outlook(self):
        src = next(s for s in build_data.SOURCES if s["id"] == "spc-outlook")
        feat = lambda lab: {"properties": {"LABEL": lab, "ISSUE_ISO": "2026-11-14T05:15:00+00:00", "EXPIRE_ISO": "2026-11-15T12:00:00+00:00"},
                            "geometry": {"type": "Polygon", "coordinates": [[[-100, 30], [-90, 30], [-90, 40], [-100, 40], [-100, 30]]]}}
        ev = build_data.parse_spc({"features": [feat("TSTM"), feat("ENH"), feat("HIGH")]}, src)
        self.assertEqual([e["severity"] for e in ev], ["moderate", "extreme"])
        self.assertEqual(ev[0]["lat"], 35.0)
        ev[0]["summary"] = lib.summarize(ev[0])
        self.assertTrue(lib.guard_ok(ev[0]["summary"], ev[0]), ev[0]["summary"])

    def test_hms_smoke(self):
        src = next(s for s in build_data.SOURCES if s["id"] == "hms-smoke")
        ev = build_data.parse_hms(open(os.path.join(FIX, "hms-smoke.kml")).read(), src)
        self.assertTrue(ev)
        for e in ev:
            self.assertTrue(lib.guard_ok(lib.summarize(e), e), lib.summarize(e))
            self.assertIn(e["detail"]["density"], ("Medium", "Heavy"))

    def test_faa_and_ms365(self):
        sf = next(x for x in build_data.SOURCES if x["id"] == "atd-faa")
        d = {"updated_utc": "2026-11-14T11:54:22Z", "events": [
            {"code": "ATL", "name": "ATL", "kind": "ground_stop", "reason": "thunderstorms", "avg": None, "max": None, "end_time": "Nov 14 at 14:15 UTC.", "status": "OFFICIAL"},
            {"code": "ORD", "name": "ORD", "kind": "delay", "reason": "volume", "avg": 45, "max": 60, "end_time": None, "status": "OFFICIAL"}]}
        build_data.FIXTURE_MODE, build_data.FIXTURE_DIR = True, FIX
        ev = build_data.parse_faa(d, sf)
        self.assertEqual([e["severity"] for e in ev], ["severe", "moderate"])
        self.assertEqual(ev[0]["lat"], 33.64)
        for e in ev:
            e["summary"] = lib.summarize(e)
            self.assertTrue(lib.guard_ok(e["summary"], e), e["summary"])
        sm = next(x for x in build_data.SOURCES if x["id"] == "ms365")
        o = build_data.parse_ms365({"status": "Service degradation", "current": {"id": "2026-11-14", "start": "2026-11-14T08:00:00Z"}, "incidents": []}, sm)
        self.assertEqual(o[0]["type"], "outage")
        o[0]["summary"] = lib.summarize(o[0])
        self.assertTrue(lib.guard_ok(o[0]["summary"], o[0]), o[0]["summary"])

    def test_service_worker_scope(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sw = open(os.path.join(root, "sw.js")).read()
        self.assertIn("url.origin !== self.location.origin", sw)
        self.assertNotIn("http://", sw.replace("http://www", ""))
        self.assertIn("cache sentence", "cache sentence" if "caches its own files" in open(os.path.join(root, "privacy.html")).read() else "")

    def test_gdelt_clusters_and_statements(self):
        src = next(s for s in build_data.SOURCES if s["id"] == "gdelt-doc")
        ev = build_data.parse_gdelt(json.load(open(os.path.join(FIX, "gdelt-doc.json"))), src)
        self.assertEqual(len(ev), 2)
        top = ev[0]
        self.assertEqual(top["detail"]["outlets"], 4)
        self.assertEqual(len(top["links"]), 3)
        self.assertEqual(len({l["label"] for l in top["links"]}), 3)
        for e in ev:
            e["summary"] = lib.summarize(e)
            self.assertTrue(lib.guard_ok(e["summary"], e), e["summary"])
            self.assertTrue(all(l["url"].startswith("https://") for l in e["links"]))
        sf = next(s for s in build_data.SOURCES if s["id"] == "fcdo")
        st = build_data.parse_fcdo(open(os.path.join(FIX, "fcdo.xml")).read(), sf)
        self.assertTrue(0 < len(st) <= 6)
        self.assertTrue(all(e["title"].startswith("UK Foreign Office: ") and e["source_url"].startswith("https://") for e in st))

    def test_tv_excludes_world_events(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertIn("e.type!=='statement'&&e.type!=='headline'", open(os.path.join(root, "tv.html")).read())

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
