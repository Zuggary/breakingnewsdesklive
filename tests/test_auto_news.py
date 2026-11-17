"""Automatic major-news proposals: internal, gated, labelled Unverified lead until a person reads a primary source."""
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import auto_news, tipwatch, manual_items, claims  # noqa: E402

NOW = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)


def cand(items):
    return {"lead": "lead-x", "first_seen": "2026-11-17T00:10:00Z", "n_outlets": len(items), "outlets": sorted({i["feed"] for i in items}), "items": items}


def it(feed, title, t="2026-11-17T00:10:00Z"):
    return {"feed": feed, "title": title, "link": "https://%s.example/1" % feed, "time": t}


GOOD = cand([it("cnn", "US intelligence: Iran weighing dirty bomb or chemical attack on officials in Washington"),
             it("guardian", "Iran weighing dirty bomb or chemical attack on US officials in Washington, report says", "2026-11-17T00:20:00Z"),
             it("nbc", "White House says no credible threats after report Iran weighing dirty bomb attack on officials", "2026-11-17T00:30:00Z")])


class Gates(unittest.TestCase):
    def test_a_story_with_2_top_outlets_and_a_response_is_ready(self):
        p = auto_news.propose(GOOD, NOW)
        self.assertTrue(p["ready"], p["reasons"])
        self.assertEqual(p["item"]["responses"][0]["who"], "White House")
        self.assertEqual(p["item"]["responses"][0]["text"], "says no credible threats")

    def test_fewer_than_2_top_outlets_is_not_ready(self):
        p = auto_news.propose(cand([it("nbc", "White House says no credible threats after attack report"), it("gdelt-domain.example", "Attack report on officials")]), NOW)
        self.assertFalse(p["ready"])
        self.assertTrue(any("top outlets" in r for r in p["reasons"]))

    def test_no_official_response_line_is_not_ready(self):
        p = auto_news.propose(cand([it("cnn", "Explosion reported near stadium"), it("bbc", "Explosion near stadium, police on scene")]), NOW)
        self.assertFalse(p["ready"])
        self.assertTrue(any("response" in r for r in p["reasons"]))

    def test_no_outlet_headline_is_copied_into_the_item(self):
        p = auto_news.propose(GOOD, NOW)
        blob = (p["item"]["title"] + " " + p["item"]["summary"]).lower()
        for i in GOOD["items"]:
            self.assertNotIn(i["title"].lower(), blob)
            self.assertNotIn(i["title"].lower()[:40], blob)

    def test_the_label_is_never_above_unverified_lead(self):
        item = auto_news.propose(GOOD, NOW)["item"]
        ev = manual_items.to_event(item, NOW)
        self.assertEqual(ev["detail"]["label"], claims.UNVERIFIED)
        self.assertFalse(claims.ticker_ok({"label": ev["detail"]["label"]}))

    def test_washington_never_appears_without_dc(self):
        p = auto_news.propose(GOOD, NOW)
        self.assertNotIn("Washington", p["item"]["title"])

    def test_the_item_passes_the_curated_validator_and_expires_in_48_hours(self):
        item = auto_news.propose(GOOD, NOW)["item"]
        self.assertEqual(manual_items.validate(item), [])
        self.assertEqual(item["expires"], "2026-11-19T00:10:00Z")


class Model(unittest.TestCase):
    def test_a_model_sentence_is_used_only_when_it_passes_the_word_guard(self):
        titles = [i["title"] for i in GOOD["items"]]
        ok = auto_news.propose(GOOD, NOW, lambda t: "Iran is reported to be weighing a dirty bomb attack on officials.")
        self.assertIn("weighing a dirty bomb", ok["item"]["summary"])
        invented = auto_news.propose(GOOD, NOW, lambda t: "Iran has already moved 40 operatives into Moscow.")
        self.assertNotIn("Moscow", invented["item"]["summary"])
        alarm = auto_news.propose(GOOD, NOW, lambda t: "Terrifying plot by Iran against officials.")
        self.assertNotIn("Terrifying", alarm["item"]["summary"])
        self.assertTrue(auto_news.word_guard("Iran weighing attack on officials", titles))
        self.assertFalse(auto_news.word_guard("Iran moved 99 troops", titles))

    def test_the_summary_always_says_the_desk_has_not_confirmed_it(self):
        self.assertIn("The desk has not confirmed it.", auto_news.propose(GOOD, NOW)["item"]["summary"])
        self.assertIn("The desk has not confirmed it.", auto_news.propose(GOOD, NOW, lambda t: "Iran is reported to be weighing a dirty bomb attack on officials.")["item"]["summary"])


class Internal(unittest.TestCase):
    def test_proposals_are_written_only_outside_the_repo(self):
        src = open(os.path.join(ROOT, "tools", "tipwatch.py"), encoding="utf-8").read()
        self.assertIn("proposed-items.json", src)
        self.assertTrue(os.path.realpath(tipwatch.DEFAULT_DIR).startswith(os.path.realpath(ROOT)) is False)
        for name in ("tools/build_data.py", "app.js", "index.html", "sw.js"):
            self.assertNotIn("auto_news", open(os.path.join(ROOT, name), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
