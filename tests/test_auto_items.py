"""Auto ingestion uses fictional reporting and no network or model clients."""
import ast
import copy
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tools import auto_items, build_data, claims, manual_items

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ITEM = auto_items.load(FIXTURES / "auto-items.json")[0]
NOW = datetime(2026, 11, 17, 2, tzinfo=timezone.utc)


class AutoItems(unittest.TestCase):
    def test_valid_item_and_build_label(self):
        self.assertEqual(auto_items.gate(ITEM, NOW), [])
        events, status = build_data.build(str(FIXTURES), NOW)
        event = next(e for e in events if e["id"] == ITEM["id"])
        self.assertTrue(event["auto"])
        self.assertTrue(event["detail"]["auto"])
        self.assertEqual(event["detail"]["lane"], "curated")
        expected = manual_items.to_event(ITEM, NOW)["detail"]["label"]
        self.assertIn(expected, (claims.CORROBORATED, claims.UNVERIFIED))
        self.assertEqual(event["confidence"], expected)
        self.assertEqual(event["detail"]["label"], expected)
        record = next(s for s in status if s["id"] == "auto-items")
        self.assertTrue(record["ok"])
        self.assertEqual((record["count"], record["rejected"]), (1, 0))

    def bad_items(self):
        changes = [
            {"sources": ITEM["sources"][:1]},
            {"sources": [dict(ITEM["sources"][0], url="https://wftv.com/example"),
                         dict(ITEM["sources"][1], url="https://kiro7.com/example")]},
            {"responses": []},
            {"summary": "Fictional outlets report a network interruption."},
            {"title": "BREAKING: network interruption"},
            {"expires": "2026-11-17T01:30:00Z"},
            {"expires": "2026-11-21T01:00:00Z"},
            {"id": "manual-example"},
            {"time": "2026-11-17T03:00:01Z"},
            {"sources": [dict(s, kind="lead") for s in ITEM["sources"]]},
            {"sources": [dict(s, verification="tentative") for s in ITEM["sources"]]},
            {"exclusive_confirmed": True, "sources": [dict(ITEM["sources"][0], scope="exclusive")]},
        ]
        return [dict(copy.deepcopy(ITEM), **change) for change in changes]

    def test_every_gate_rejects_and_build_counts(self):
        bad = self.bad_items()
        for item in bad:
            with self.subTest(item=item):
                self.assertTrue(auto_items.gate(item, NOW))
                self.assertEqual(auto_items.active([item], NOW), [])
        with patch.object(auto_items, "load", return_value=bad + [ITEM]):
            events, status = build_data.build(str(FIXTURES), NOW)
        record = next(s for s in status if s["id"] == "auto-items")
        self.assertTrue(record["ok"])
        self.assertEqual((record["count"], record["rejected"]), (1, len(bad)))
        self.assertEqual(len([e for e in events if e.get("auto")]), 1)

    def test_load_missing_invalid_and_wrong_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auto-items.json"
            self.assertEqual(auto_items.load(path), [])
            for contents in ('{', '{}', 'null', '["bad", null, {}]'):
                path.write_text(contents)
                items = auto_items.load(path)
                self.assertEqual(auto_items.active(items, NOW), [])
                with patch.object(auto_items, "load", return_value=items):
                    _, status = build_data.build(str(FIXTURES), NOW)
                record = next(s for s in status if s["id"] == "auto-items")
                self.assertTrue(record["ok"])
                self.assertEqual(record["count"], 0)

    def test_newest_ten_and_time_boundaries(self):
        items = [dict(copy.deepcopy(ITEM), id="auto-%s" % i,
                      time=(NOW - timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")) for i in range(15)]
        self.assertEqual([i["id"] for i in auto_items.active(items[::-1], NOW)],
                         ["auto-%s" % i for i in range(10)])
        self.assertEqual(auto_items.gate(dict(ITEM, time="2026-11-17T03:00:00Z"), NOW), [])
        self.assertEqual(auto_items.gate(dict(ITEM, expires="2026-11-20T01:00:00Z"), NOW), [])
        self.assertTrue(auto_items.gate(dict(ITEM, expires="2026-11-17T02:00:00Z"), NOW))

    def test_manual_ids_take_precedence(self):
        original = build_data.probes.load_json
        def load(path, default):
            if os.path.basename(path) == "manual-items.json":
                return [ITEM]
            return original(path, default)
        with patch.object(build_data.probes, "load_json", side_effect=load):
            events, status = build_data.build(str(FIXTURES), NOW)
        matches = [e for e in events if e["id"] == ITEM["id"]]
        self.assertEqual(len(matches), 1)
        self.assertNotIn("auto", matches[0])
        self.assertEqual(next(s for s in status if s["id"] == "auto-items")["count"], 0)

    def test_workflow_fetch_before_build(self):
        workflow = (FIXTURES.parent.parent / ".github/workflows/pages.yml").read_text()
        self.assertLess(workflow.index("name: Fetch the auto items"), workflow.index("name: Build event data"))
        self.assertIn("git fetch --depth 1 origin news-data && git show FETCH_HEAD:auto_items.json > data/auto_items.json || rm -f data/auto_items.json", workflow)

    def test_only_stdlib_and_shared_helpers_imported(self):
        tree = ast.parse(Path(auto_items.__file__).read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module)
                if node.module == "tools":
                    self.assertEqual({alias.name for alias in node.names}, {"claims", "manual_items"})
        self.assertEqual(set(imports), {"json", "datetime", "urllib.parse", "tools"})


class AutoItemsAreNotExemptFromTheKillSwitch(unittest.TestCase):
    def test_an_auto_item_with_a_crisis_word_is_held_for_a_person(self):
        from tools import killswitch
        ev = {"id": "auto-1", "type": "security", "title": "Reported attack on officials", "place": "x", "source": "s", "curated": True, "auto": True}
        out, held = killswitch.apply([ev], set())
        self.assertEqual((len(out), len(held)), (0, 1))

    def test_a_manual_curated_item_is_still_exempt(self):
        from tools import killswitch
        ev = {"id": "m-1", "type": "security", "title": "Reported attack on officials", "place": "x", "source": "s", "curated": True}
        out, held = killswitch.apply([ev], set())
        self.assertEqual((len(out), len(held)), (1, 0))
