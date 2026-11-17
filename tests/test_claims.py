"""GD8 part 3: claim labels, independent chains, the ticker gate and the narration queue."""
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import claims, build_data  # noqa: E402

NOW = datetime(2026, 11, 16, 23, 0, tzinfo=timezone.utc)


def claim(ctype="outage", evidence=(), flags=None, cid="c1", text="Chase login problems"):
    c = {"id": cid, "type": ctype, "text": text, "evidence": [dict(kind=k, origin=o, url="https://x/" + (o or "")) for k, o in evidence], "flags": flags or {}}
    c["label"] = claims.label(c)
    return c


class Labels(unittest.TestCase):
    def test_no_evidence_is_a_lead(self):
        self.assertEqual(claims.label(claim()), claims.UNVERIFIED)

    def test_one_outlet_chain_is_never_corroborated(self):
        self.assertEqual(claims.label(claim(evidence=[("outlet", "nbc.com")])), claims.UNVERIFIED)

    def test_one_official_chain_is_official_single_source(self):
        self.assertEqual(claims.label(claim(evidence=[("official", "united-airlines")])), claims.OFFICIAL)

    def test_two_independent_chains_are_corroborated(self):
        self.assertEqual(claims.label(claim(evidence=[("outlet", "nbc.com"), ("outlet", "bbc.co.uk")])), claims.CORROBORATED)

    def test_two_copies_of_one_origin_count_as_one_chain(self):
        c = claim(evidence=[("outlet", "nbc.com"), ("outlet", "nbc.com")])
        self.assertEqual(len(claims.chains(c)), 1)
        self.assertEqual(claims.label(c), claims.UNVERIFIED)

    def test_sister_outlets_share_one_chain(self):
        for pair in (("wftv.com", "wsoctv.com"), ("aol.com", "yahoo.com")):
            o = {claims.origin_of(d) for d in pair}
            self.assertEqual(len(o), 1, pair)
        c = claim(evidence=[("outlet", claims.origin_of("wftv.com")), ("outlet", claims.origin_of("kiro7.com"))])
        self.assertEqual(claims.label(c), claims.UNVERIFIED)

    def test_a_named_wire_origin_overrides_the_outlet(self):
        self.assertEqual(claims.origin_of("nbc.com", stated="AP"), claims.origin_of("bbc.co.uk", stated="ap"))

    def test_unknown_origins_are_the_same_chain(self):
        c = claim(evidence=[("outlet", None), ("outlet", "")])
        self.assertEqual(claims.chains(c), {"unknown"})
        self.assertEqual(claims.label(c), claims.UNVERIFIED)
        self.assertEqual(claims.label(claim(evidence=[("outlet", None), ("outlet", "bbc.co.uk")])), claims.CORROBORATED)  # unknown + a known origin are two chains

    def test_a_lead_is_never_evidence(self):
        c = claim(evidence=[("lead", "bluesky"), ("lead", "live-stream"), ("lead", "tip-feed")])
        self.assertEqual(claims.chains(c), set())
        self.assertEqual(claims.label(c), claims.UNVERIFIED)
        c = claim(evidence=[("outlet", "nbc.com"), ("lead", "live-stream")])
        self.assertEqual(claims.label(c), claims.UNVERIFIED)

    def test_a_probe_measurement_counts_only_for_a_page_error_claim(self):
        ev = [("official", "provider"), ("measurement", "desk-probe")]
        self.assertEqual(claims.label(claim(ctype="page-error", evidence=ev)), claims.CORROBORATED)
        self.assertEqual(claims.label(claim(ctype="cause", evidence=ev)), claims.OFFICIAL)
        self.assertEqual(claims.label(claim(ctype="page-error", evidence=[("measurement", "desk-probe")])), claims.UNVERIFIED)

    def test_precedence(self):
        ev = [("outlet", "nbc.com"), ("outlet", "bbc.co.uk")]
        self.assertEqual(claims.label(claim(evidence=ev, flags={"resolved": True})), claims.RESOLVED)
        self.assertEqual(claims.label(claim(evidence=ev, flags={"resolved": True, "contested": True})), claims.CONTESTED)
        self.assertEqual(claims.label(claim(evidence=ev, flags={"resolved": True, "contested": True, "corrected": True})), claims.CORRECTED)


class Lifecycle(unittest.TestCase):
    def test_history_records_each_label_change(self):
        c = claim()
        claims.add_evidence(c, "outlet", "nbc.com", "https://nbc.example/a", NOW)
        claims.add_evidence(c, "outlet", "bbc.co.uk", "https://bbc.example/a", NOW)
        self.assertEqual(c["label"], claims.CORROBORATED)
        self.assertEqual([(h["from"], h["to"]) for h in c["history"]], [(claims.UNVERIFIED, claims.CORROBORATED)])

    def test_a_withdrawn_chain_drops_the_claim_one_level_and_leaves_the_queue(self):
        c = claim(evidence=[("outlet", "nbc.com"), ("outlet", "bbc.co.uk")])
        q = claims.Queue()
        self.assertEqual(q.sync([c], NOW), [("added", "c1")])
        claims.withdraw(c, "bbc.co.uk", NOW)
        self.assertEqual(c["label"], claims.UNVERIFIED)
        self.assertEqual(q.sync([c], NOW), [("removed", "c1")])
        self.assertEqual(q.entries, {})


class Lessons(unittest.TestCase):
    """CoS lessons from the Agenda-Free TV coverage of the 16 Nov United outage."""

    def test_evidence_keeps_source_intermediary_time_scope_and_verification_apart(self):
        c = claim()
        claims.add_evidence(c, "official", "United Airlines", "https://united.example/s", NOW, intermediary="CBS News correspondent",
                            published="2026-11-16T23:02:00Z", scope="departures only", verification="attributed", text="Technology issue resolved")
        ev = c["evidence"][0]
        for k in ("source", "intermediary", "published", "observed", "scope", "verification", "kind", "url"):
            self.assertIn(k, ev)
        self.assertEqual(ev["source"], "United Airlines")
        self.assertEqual(ev["intermediary"], "CBS News correspondent")
        self.assertEqual(ev["scope"], "departures only")
        self.assertEqual(ev["verification"], "attributed")
        self.assertEqual(ev["published"], "2026-11-16T23:02:00Z")
        self.assertEqual(ev["observed"], "2026-11-16T23:00:00Z")

    def test_two_intermediaries_relaying_one_source_are_one_chain(self):
        c = claim()
        claims.add_evidence(c, "official", "United Airlines", "https://a", NOW, intermediary="CBS", verification="attributed")
        claims.add_evidence(c, "official", "United Airlines", "https://b", NOW, intermediary="Reuters", verification="attributed")
        self.assertEqual(claims.chains(c), {"United Airlines"})
        self.assertEqual(claims.label(c), claims.UNVERIFIED)

    def test_an_attributed_statement_stays_a_lead_until_read_directly(self):
        c = claim()
        claims.add_evidence(c, "official", "United Airlines", "https://a", NOW, intermediary="CBS", verification="attributed")
        self.assertEqual(c["label"], claims.UNVERIFIED)
        claims.add_evidence(c, "official", "United Airlines", "https://united.example/newsroom", NOW, verification="direct")
        self.assertEqual(c["label"], claims.OFFICIAL)
        claims.add_evidence(c, "outlet", "bbc.co.uk", "https://bbc.example", NOW)
        self.assertEqual(c["label"], claims.CORROBORATED)

    def test_user_reports_such_as_downdetector_are_never_proof(self):
        c = claim(evidence=[("user-reports", "downdetector-style"), ("user-reports", "social-complaints")])
        self.assertEqual(claims.chains(c), set())
        self.assertEqual(claims.label(c), claims.UNVERIFIED)
        c = claim(evidence=[("outlet", "nbc.com"), ("user-reports", "downdetector-style")])
        self.assertEqual(claims.label(c), claims.UNVERIFIED)

    def test_a_disappeared_notice_is_not_a_resolution(self):
        c = claim(ctype="page-error", evidence=[("official", "United Airlines"), ("outlet", "bbc.co.uk")])
        before = c["label"]
        self.assertTrue(claims.note_disappeared(c, "United Airlines", NOW))
        claims.revise(c, NOW, "recheck")
        self.assertEqual(c["label"], before)
        self.assertFalse(c["flags"].get("resolved"))
        self.assertIn("A removed notice is not a resolution.", " ".join(c["notes"]))
        self.assertTrue(any("not a resolution" in h["why"] for h in c["history"]))
        self.assertFalse(claims.note_disappeared(claim(), "Nobody", NOW))

    def test_chat_and_stream_tips_wait_and_never_air(self):
        q = claims.TipQueue()
        q.queue("t1", "viewer says Nashville departure left at 4:41", "chat", NOW)
        q.queue("t2", "United says issue fixed", "live-stream", NOW)
        self.assertEqual(q.airable(), [])
        self.assertEqual(q.tips["t1"]["state"], "queued")
        c = claim(cid="c9", ctype="page-error")
        with self.assertRaises(ValueError):
            q.promote("t2", c, "lead", "live-stream", "", NOW)
        q.promote("t2", c, "official", "United Airlines", "https://united.example/newsroom", NOW, verification="direct")
        self.assertEqual(q.tips["t2"]["state"], "checked")
        self.assertEqual(c["label"], claims.OFFICIAL)
        self.assertEqual(q.airable(), [])
        qq = claims.Queue()
        qq.sync([c], NOW)
        self.assertEqual(qq.entries, {})            # one official chain does not pass the strict ticker

    def test_watch_plan_checks_social_newsroom_and_wires_together(self):
        p = claims.watch_plan("united")
        self.assertTrue(p["social"] and p["newsroom"] and p["wires"] and p["official_status"])
        self.assertIn("hub.united.com", p["newsroom"])
        self.assertEqual(claims.watch_plan("unknown-service")["wires"], ["AP", "Reuters"])


class Gate(unittest.TestCase):
    def test_only_corroborated_claims_pass_the_strict_ticker(self):
        labels = {claims.UNVERIFIED: False, claims.OFFICIAL: False, claims.CORROBORATED: True, claims.CONTESTED: False, claims.CORRECTED: False, claims.RESOLVED: False}
        for lab, expect in labels.items():
            self.assertEqual(claims.ticker_ok({"label": lab}), expect, lab)
        self.assertTrue(claims.ticker_ok({"label": claims.OFFICIAL}, strict=False))

    def test_the_queue_takes_only_corroborated_claims(self):
        cs = [claim(cid="a", evidence=[("outlet", "nbc.com"), ("outlet", "bbc.co.uk")]), claim(cid="b", evidence=[("outlet", "nbc.com")]),
              claim(cid="c", evidence=[("official", "agency")]), claim(cid="d", evidence=[("lead", "live-stream")])]
        q = claims.Queue()
        q.sync(cs, NOW)
        self.assertEqual(sorted(q.entries), ["a"])

    def test_a_changed_claim_replaces_its_queue_entry_with_a_what_changed_line(self):
        c = claim(evidence=[("outlet", "nbc.com"), ("outlet", "bbc.co.uk")], text="United departures halted")
        q = claims.Queue()
        q.sync([c], NOW)
        c["text"] = "United says departures are resuming"
        self.assertEqual(q.sync([c], NOW), [("replaced", "c1")])
        e = q.entries["c1"]
        self.assertEqual(e["text"], "United says departures are resuming")
        self.assertIn("Changed from", e["what_changed"])
        self.assertIn("United departures halted", e["what_changed"])

    def test_a_correction_removes_the_claim_from_the_queue(self):
        c = claim(evidence=[("outlet", "nbc.com"), ("outlet", "bbc.co.uk")])
        q = claims.Queue()
        q.sync([c], NOW)
        claims.set_flag(c, "corrected", NOW, "Wrong airline")
        self.assertEqual(q.sync([c], NOW), [("removed", "c1")])


class Built(unittest.TestCase):
    def test_built_events_carry_a_label_and_a_ticker_flag(self):
        events, _ = build_data.build(os.path.join(ROOT, "tests", "fixtures"), datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
        for e in events:
            self.assertIn(e["confidence"], claims.PRECEDENCE, e["title"])
            self.assertEqual(e["ticker_ok"], e["confidence"] == claims.CORROBORATED)
        self.assertTrue(any(e["confidence"] == claims.OFFICIAL for e in events))

    def test_news_item_with_probe_and_independent_outlets_is_corroborated(self):
        item = {"id": "news-x", "title": "News reports: Chase problems reported by 2 outlets", "time": "2026-11-16T22:00:00Z",
                "detail": {"lane": "news", "outlet_domains": ["nbc.com", "bbc.co.uk"], "probes": []}, "links": []}
        self.assertEqual(claims.confidence_for_event(item), claims.CORROBORATED)
        item["detail"]["outlet_domains"] = ["wftv.com", "wsoctv.com"]
        self.assertEqual(claims.confidence_for_event(item), claims.UNVERIFIED)
        item["detail"]["probes"] = [{"service": "Chase", "status": "down", "since": "2026-11-16T21:50:00Z"}]
        self.assertEqual(claims.confidence_for_event(item), claims.CORROBORATED)    # one syndicated chain plus our measurement

    def test_the_stream_crawl_uses_the_ticker_flag(self):
        tv = open(os.path.join(ROOT, "tv.html"), encoding="utf-8").read()
        self.assertIn("e.ticker_ok!==false", tv)

    def test_no_model_client_in_claims(self):
        import re
        src = open(os.path.join(ROOT, "tools", "claims.py"), encoding="utf-8").read()
        imports = " ".join(re.findall(r"^\s*(?:import|from)\s+(\S+)", src, re.M)).lower()
        for bad in ("anthropic", "openai", "google", "genai", "claude", "gemini", "requests", "subprocess"):
            self.assertNotIn(bad, imports)


if __name__ == "__main__":
    unittest.main()
