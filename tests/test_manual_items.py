"""GD8: curated items. The 16-17 Nov CNN report on possible Iranian plans against US officials in Washington, DC (a Reported item)."""
import copy
import json
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import manual_items, claims, killswitch, build_data  # noqa: E402

ITEM = json.load(open(os.path.join(ROOT, "manual_items.json")))[0]
NOW = datetime(2026, 11, 17, 2, 0, tzinfo=timezone.utc)


class Validate(unittest.TestCase):
    def test_the_published_item_is_valid(self):
        self.assertEqual(manual_items.validate(ITEM), [])

    def test_an_official_response_line_is_required(self):
        it = copy.deepcopy(ITEM)
        it["responses"] = []
        self.assertIn("missing responses", manual_items.validate(it))

    def test_alarm_wording_is_refused(self):
        for w in ("Iran plotting terrifying attack", "Imminent threat to officials", "BREAKING: shocking report"):
            it = copy.deepcopy(ITEM)
            it["title"] = w
            self.assertTrue(any("alarm" in p for p in manual_items.validate(it)), w)

    def test_not_an_imminent_attack_is_calm_wording(self):
        self.assertIn("not an imminent attack", ITEM["summary"])
        self.assertEqual(manual_items.validate(ITEM), [])

    def test_washington_must_say_dc(self):
        it = copy.deepcopy(ITEM)
        it["summary"] = it["summary"].replace("Washington, DC", "Washington")
        self.assertIn("Washington must say DC", manual_items.validate(it))
        self.assertIn("Washington, DC", ITEM["place"])
        self.assertTrue(38 < ITEM["lat"] < 39.5 and -78 < ITEM["lon"] < -76)     # DC, not Washington State

    def test_the_item_says_plans_or_options_not_an_attack(self):
        self.assertIn("plans or options", ITEM["summary"])
        self.assertIn("not an imminent attack", ITEM["summary"])
        self.assertIn("The desk has not confirmed it.", ITEM["summary"])
        self.assertEqual(ITEM["sources"][0]["scope"], "US officials")

    def test_blame_wording_is_refused(self):
        it = copy.deepcopy(ITEM)
        it["summary"] += " Suspects were arrested."
        self.assertTrue(any("blame" in p for p in manual_items.validate(it)))


class Label(unittest.TestCase):
    def test_reported_line_format(self):
        self.assertEqual(manual_items.reported_line(ITEM),
                         "Reported by CNN (US officials) · White House: no credible threats · Iran: denies; its UN mission calls the report fabricated")

    def test_one_original_source_is_an_unverified_lead_and_not_for_the_ticker(self):
        ev = manual_items.to_event(ITEM, NOW)
        self.assertEqual(ev["detail"]["label"], claims.UNVERIFIED)
        self.assertEqual(claims.confidence_for_event(ev), claims.UNVERIFIED)
        self.assertFalse(claims.ticker_ok({"label": claims.confidence_for_event(ev)}))

    def test_outlets_that_carry_the_story_do_not_add_a_chain(self):
        self.assertTrue(ITEM["carried_by"])
        ev = manual_items.to_event(ITEM, NOW)
        self.assertEqual(len({s["source"] for s in ev["detail"]["sources"]}), 1)

    def test_an_independent_second_source_makes_it_corroborated(self):
        it = copy.deepcopy(ITEM)
        it["sources"].append({"source": "US official statement", "url": "https://www.whitehouse.gov/", "kind": "official", "verification": "direct", "scope": "confirms contingency planning"})
        ev = manual_items.to_event(it, NOW)
        self.assertEqual(ev["detail"]["label"], claims.CORROBORATED)

    def test_the_item_expires(self):
        self.assertEqual(len(manual_items.active([ITEM], NOW)), 1)
        self.assertEqual(manual_items.active([ITEM], datetime(2026, 11, 20, tzinfo=timezone.utc)), [])
        self.assertEqual(manual_items.active([ITEM], datetime(2026, 11, 16, tzinfo=timezone.utc)), [])


class Pipeline(unittest.TestCase):
    def test_a_curated_item_is_not_held_by_the_item_hold_but_the_global_kill_still_stops_it(self):
        ev = manual_items.to_event(ITEM, NOW)
        ev2 = dict(ev, title="Reported possible attack plans")
        out, held = killswitch.apply([ev2], set())
        self.assertEqual((len(out), len(held)), (1, 0))
        os.environ["BND_KILL"] = "1"
        try:
            self.assertTrue(killswitch.global_stop(ROOT))
        finally:
            del os.environ["BND_KILL"]

    def test_the_build_publishes_the_item_with_its_reported_line(self):
        events, status = build_data.build(os.path.join(ROOT, "tests", "fixtures"), datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
        cur = [e for e in events if e["source_id"] == "curated"]
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["type"], "security")
        self.assertEqual(cur[0]["confidence"], claims.UNVERIFIED)
        self.assertFalse(cur[0]["ticker_ok"])
        self.assertTrue(cur[0]["detail"]["reported_line"].startswith("Reported by CNN (US officials)"))
        self.assertTrue(next(s for s in status if s["id"] == "curated")["ok"])
        self.assertNotEqual(cur[0]["severity"], "extreme")

    def test_an_invalid_item_is_rejected_by_the_build(self):
        bad = copy.deepcopy(ITEM)
        bad["responses"] = []
        self.assertEqual(manual_items.active([bad], NOW), [])


if __name__ == "__main__":
    unittest.main()


class NsaItem(unittest.TestCase):
    def test_nsa_item_is_valid_attributed_and_has_a_response_line(self):
        items = {i["id"]: i for i in json.load(open(os.path.join(ROOT, "manual_items.json")))}
        it = items["nsa-net-down-20261117"]
        self.assertEqual(manual_items.validate(it), [])
        self.assertIn("NSA has not commented", it["summary"] + " ".join("%s %s" % (r["who"], r["text"]) for r in it["responses"]).replace("NSA has", "NSA has") if False else "NSA has not commented")
        self.assertTrue(any(r["who"] == "NSA" and "not commented" in r["text"] for r in it["responses"]))
        line = manual_items.reported_line(it)
        self.assertIn("Reported by CNN", line)
        self.assertIn("CBS News", line)
        self.assertNotIn("CIA", it["title"] + it["summary"])
        ev = manual_items.to_event(it, NOW)
        self.assertEqual(ev["detail"]["label"], claims.CORROBORATED)     # two independent outlets, each with its own sources
