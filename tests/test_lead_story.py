"""The lead story feed: data/lead-story.json for a stream VJ."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import lead_story, build_data  # noqa: E402

FX = os.path.join(ROOT, "tests", "fixtures")
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def ev(i, **kw):
    e = {"id": i, "title": "Title " + i, "summary": "First sentence. Second sentence. Third sentence.", "confidence": "Unverified lead", "ticker_ok": False,
         "time": "2026-11-14T10:00:00Z", "severity": "moderate", "source": "Src", "source_url": "https://s.example/" + i, "place": "Somewhere", "detail": {}}
    e.update(kw)
    return e


class Pick(unittest.TestCase):
    def test_two_lines_keeps_two_sentences(self):
        self.assertEqual(lead_story.two_lines("One. Two. Three."), "One. Two.")
        self.assertTrue(len(lead_story.two_lines("word " * 200)) <= 244)

    def test_big_then_curated_then_news_then_top_event(self):
        a, b, c, d = ev("a"), ev("b", detail={"lane": "news"}, links=[]), ev("c", curated=True, detail={"lane": "curated", "sources": []}), ev("d", big=True, detail={"lane": "news"}, links=[])
        self.assertEqual(lead_story.build([a, b, c, d], "T")["lead"]["id"], "d")
        self.assertEqual(lead_story.build([a, b, c], "T")["lead"]["id"], "c")
        self.assertEqual(lead_story.build([a, b], "T")["lead"]["id"], "b")
        self.assertEqual(lead_story.build([a], "T")["lead"]["id"], "a")
        self.assertIsNone(lead_story.build([], "T")["lead"])

    def test_story_fields(self):
        f = lead_story.build([ev("a"), ev("b")], "2026-11-14T12:00:00Z")
        s = f["lead"]
        for k in ("headline", "summary", "label", "sources", "updated", "kind", "reported_line"):
            self.assertIn(k, s)
        self.assertEqual(f["as_of"], "2026-11-14T12:00:00Z")
        self.assertEqual(s["summary"], "First sentence. Second sentence.")
        self.assertEqual(len(f["next"]), 1)

    def test_news_sources_are_outlet_names_and_links_never_headlines(self):
        e = ev("n", detail={"lane": "news"}, links=[{"label": "nbc.com", "title": "An outlet headline that must not be copied", "url": "https://nbc.example/1"}])
        s = lead_story.story(e)
        self.assertEqual(s["sources"], [{"name": "nbc.com", "intermediary": None, "url": "https://nbc.example/1"}])
        self.assertNotIn("must not be copied", json.dumps(s))


class Built(unittest.TestCase):
    def test_main_writes_the_feed_with_a_labelled_lead(self):
        with tempfile.TemporaryDirectory() as d:
            old = sys.argv
            sys.argv = ["build_data.py", "--out", d, "--fixtures", FX]
            try:
                build_data.main()
            finally:
                sys.argv = old
            f = json.load(open(os.path.join(d, "lead-story.json")))
        self.assertTrue(f["lead"])
        self.assertIn(f["lead"]["label"], ("Unverified lead", "Official single source", "Corroborated", "Contested", "Corrected", "Resolved"))
        self.assertTrue(f["as_of"].endswith("Z"))
        self.assertTrue(f["lead"]["sources"])

    def test_the_pages_workflow_publishes_the_feed(self):
        w = open(os.path.join(ROOT, ".github", "workflows", "pages.yml"), encoding="utf-8").read()
        self.assertIn("data/lead-story.json", w)


if __name__ == "__main__":
    unittest.main()
