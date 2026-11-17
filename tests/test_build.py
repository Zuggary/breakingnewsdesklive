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
        keys = [build_data.rank_key(e) for e in self.events]
        self.assertEqual(keys, sorted(keys))

    def test_headlines_stay_out_of_the_top_15(self):
        others = [e for e in self.events if e["type"] != "headline"]
        if len(others) >= 15:
            self.assertTrue(all(e["type"] != "headline" for e in self.events[:15]))

    def test_severity_ranks_first(self):
        order = [build_data.SEV_ORDER[e["severity"]] for e in self.events if not e.get("big")]
        self.assertEqual(order, sorted(order), "a lower severity tier appears above a higher one")

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

    def test_gdelt_titles_have_no_html_entities(self):
        src = next(s for s in build_data.SOURCES if s["id"] == "gdelt-doc")
        d = json.load(open(os.path.join(FIX, "gdelt-doc.json")))
        for a in d["articles"]:
            a["title"] = "\u201c" + a["title"].replace("a", "&#xE1;", 1) + "\u201d"
        ev = build_data.parse_gdelt(d, src)
        for e in ev:
            self.assertNotIn("&#", e["title"])
            self.assertNotIn("\u201c\u201c", e["title"])
            self.assertTrue(all("&#" not in l["title"] for l in e["links"]))

    def test_tv_excludes_world_events(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertIn("e.type!=='statement'&&e.type!=='headline'", open(os.path.join(root, "tv.html")).read())

    def test_context_rules(self):
        from tools import context as cx
        now = NOW
        self.assertTrue(cx.licence_ok("CC BY 4.0"))
        self.assertTrue(cx.licence_ok("Public domain"))
        self.assertTrue(cx.licence_ok("CC0"))
        self.assertFalse(cx.licence_ok("CC BY-SA 4.0"))
        self.assertFalse(cx.licence_ok(""))
        good = {"summary": {"text": "x", "title": "Alaska", "licence": "CC BY-SA 4.0", "url": "https://en.wikipedia.org/wiki/Alaska",
                            "history_url": "https://en.wikipedia.org/w/index.php?title=Alaska&action=history"}}
        self.assertTrue(cx.validate_item(good))
        for mut in ({"licence": "CC BY 4.0"}, {"url": "http://x"}, {"text": ""}, {"history_url": ""}):
            bad = {"summary": dict(good["summary"], **mut)}
            self.assertFalse(cx.validate_item(bad), mut)
        img = {"src": "https://commons.wikimedia.org/wiki/Special:FilePath/A.jpg?width=640", "author": "Jane", "license": "CC BY 4.0",
               "credit_url": "https://commons.wikimedia.org/wiki/File:A.jpg"}
        self.assertTrue(cx.validate_item({"image": img}))
        self.assertFalse(cx.validate_item({"image": dict(img, author="")}))
        self.assertFalse(cx.validate_item({"image": dict(img, license="CC BY-SA 4.0")}))
        self.assertFalse(cx.validate_item({"image": dict(img, src="https://commons.wikimedia.org/wiki/Special:FilePath/Flag_of_X.svg")}))
        ev = {"id": "v", "type": "volcano", "place": "Observatory", "lat": 52.0, "lon": -176.0, "detail": {"volcano": "Great Sitkin"}}

        def fake(url):
            if "rest_v1" in url:
                return {"type": "standard", "title": "Great Sitkin Island", "description": "Volcanic island in Alaska",
                        "extract": "Great Sitkin Island is an uninhabited volcanic island.", "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Great_Sitkin_Island"}}}
            if "pageimages" in url:
                return {"query": {"pages": {"1": {"pageimage": "Great_Sitkin_Island.jpg"}}}}
            return {"query": {"pages": {"2": {"imageinfo": [{"extmetadata": {"LicenseShortName": {"value": "CC BY 2.0"}, "Artist": {"value": "<a>Some Author</a>"}}}]}}}}
        c = cx.build_one(ev, now, fake, {})
        self.assertEqual(c["image"]["author"], "Some Author")
        self.assertEqual(c["summary"]["licence"], "CC BY-SA 4.0")
        self.assertIn("NASA", c["satellite"]["credit"])
        wrong = dict(ev, detail={"volcano": "Paris"})
        def fake2(url):
            return {"type": "standard", "title": "Paris", "description": "Capital of France", "extract": "Paris is the capital."} if "rest_v1" in url else {}
        c2 = cx.build_one(wrong, now, fake2, {})
        self.assertNotIn("summary", c2)  # a non-volcano page is never used for a volcano

    def test_illustration_library_rules(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(root, "assets", "illustrations")
        lib = json.load(open(os.path.join(d, "library.json")))
        self.assertGreaterEqual(len(lib), 20)
        for e in lib:
            self.assertEqual(e["label"], "Illustration", e["file"])
            for k in ("prompt", "model", "date", "category"):
                self.assertTrue(e.get(k), (k, e["file"]))
            p = os.path.join(d, e["file"])
            self.assertTrue(os.path.exists(p), e["file"])
            self.assertLessEqual(os.path.getsize(p), 150 * 1024, e["file"])
            self.assertIn("no text", e["prompt"])
            self.assertIn("corner", e.get("corner_check", ""), "%s: add a corner_check note after zooming its corners for lettering or a signature" % e["file"])
        # every illustration the page can pick must exist in the library
        js = open(os.path.join(root, "lib.js")).read()
        import re
        names = set(re.findall(r"'([a-z]+-\d)'", js))
        have = {e["file"][:-5] for e in lib}
        self.assertTrue(names and names <= have, names - have)
        # the page always shows the visible tag and the caption
        self.assertIn("illus-tag", js)
        self.assertIn("It does not show the actual scene", js)

    def test_airport_context_via_wikidata(self):
        from tools import context as cx
        ev = {"id": "f", "type": "transport", "place": "Santa Ana", "lat": 33.68, "lon": -117.87, "detail": {"airport_code": "SNA"}}

        def fake(url):
            if "query.wikidata.org" in url:
                return {"results": {"bindings": [{"t": {"value": "John Wayne Airport"}}]}}
            if "rest_v1" in url:
                return {"type": "standard", "title": "John Wayne Airport", "description": "Airport in California",
                        "extract": "John Wayne Airport is a public airport.", "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/John_Wayne_Airport"}}}
            return {"query": {"pages": {"1": {}}}}
        c = cx.build_one(ev, NOW, fake, {})
        self.assertEqual(c["summary"]["title"], "John Wayne Airport")
        self.assertTrue(cx.validate_item(c))
        # a page that is not an airport is rejected
        def fake2(url):
            if "query.wikidata.org" in url:
                return {"results": {"bindings": [{"t": {"value": "Paris"}}]}}
            return {"type": "standard", "title": "Paris", "description": "Capital of France", "extract": "Paris is a city."} if "rest_v1" in url else {}
        c2 = cx.build_one(ev, NOW, fake2, {})
        self.assertNotIn("summary", c2)
        # an ambiguous code (two airports) is skipped
        def fake3(url):
            return {"results": {"bindings": [{"t": {"value": "A"}}, {"t": {"value": "B"}}]}} if "query.wikidata.org" in url else {}
        self.assertNotIn("summary", cx.build_one(ev, NOW, fake3, {}))

    def test_ambiguous_titles_show_nothing(self):
        from tools import context as cx
        dab = {"type": "disambiguation", "title": "Georgia", "description": "Topics referred to by the same term", "extract": "Georgia may refer to:"}
        self.assertFalse(cx.good_match("region", dab))
        self.assertFalse(cx.good_match("volcano", dab))
        self.assertFalse(cx.good_match("airport", dab))
        ev = {"id": "w", "type": "weather", "place": "Georgia, United States", "lat": None, "lon": None, "detail": {"state": "GA"}}
        self.assertEqual(cx.titles_for(ev), [("region", "Georgia (U.S. state)")])
        got = cx.build_one(ev, NOW, lambda u: dab if "rest_v1" in u else {}, {})
        self.assertIsNone(got)  # nothing to show, so no context key at all

    def test_faa_delay_text_does_not_break_scoring(self):
        # 2026-11-16: the FAA feed sent '2 hours and 46 minutes' as the average delay; a str crashed the data job.
        sf = next(x for x in build_data.SOURCES if x["id"] == "atd-faa")
        d = {"updated_utc": "2026-11-16T04:00:00Z", "events": [
            {"code": "SFO", "name": "SFO", "kind": "ground_delay", "reason": "low ceilings", "avg": "2 hours and 46 minutes",
             "max": "14 hours and 55 minutes", "end_time": None, "status": "OFFICIAL"}]}
        build_data.FIXTURE_MODE, build_data.FIXTURE_DIR = True, FIX
        ev = build_data.parse_faa(d, sf)
        self.assertEqual(ev[0]["detail"]["avg_delay_min"], 166)
        self.assertEqual(ev[0]["size"], 166)
        ev[0]["score"] = lib.score_event(ev[0], NOW.replace(day=16, hour=4, minute=5))
        ev[0]["summary"] = lib.summarize(ev[0])
        self.assertIn("2 hours and 46 minutes", ev[0]["summary"])
        self.assertTrue(lib.guard_ok(ev[0]["summary"], ev[0]), ev[0]["summary"])
        self.assertEqual(build_data.delay_minutes("45 minutes"), 45)
        self.assertEqual(build_data.delay_minutes("1 hour"), 60)
        self.assertIsNone(build_data.delay_minutes("n/a"))
        bad = dict(ev[0], size="garbage")
        self.assertIsInstance(lib.score_event(bad, NOW.replace(day=16, hour=4, minute=5)), float)

    def test_one_bad_event_does_not_stop_the_build(self):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        for f in os.listdir(FIX):
            shutil.copy(os.path.join(FIX, f), d)
        bad = json.load(open(os.path.join(d, "atd-faa.json")))
        bad["updated_utc"] = "2026-11-14T11:54:22Z"
        bad["events"] = [{"code": "ATL", "name": "ATL", "kind": "ground_stop", "reason": "x", "avg": {"weird": 1}, "end_time": None, "status": "OFFICIAL"}]
        json.dump(bad, open(os.path.join(d, "atd-faa.json"), "w"))
        ev, st = build_data.build(d, NOW)
        self.assertTrue(ev)

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


class HeadlineSeverity(unittest.TestCase):
    def test_outlet_headline_groups_rank_by_outlet_count(self):
        s = "Highly classified NSA comms network goes down, reports say"
        self.assertEqual(build_data._headline_severity(2, s), "minor")
        self.assertEqual(build_data._headline_severity(8, s), "moderate")
        self.assertEqual(build_data._headline_severity(19, s), "moderate")
        self.assertEqual(build_data._headline_severity(20, s), "severe")

    def test_other_topics_stay_minor_whatever_the_count(self):
        self.assertEqual(build_data._headline_severity(40, "From Batman to Bond - how Robert Pattinson landed the role"), "minor")
