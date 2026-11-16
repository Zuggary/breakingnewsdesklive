"""GD5 stock art: manifest rules and the build script (fixture image)."""
import json, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    import build_stock  # noqa: E402
    from PIL import Image  # noqa: E402
except ImportError:  # CI has no Pillow; the manifest test still runs
    build_stock = Image = None

FIELDS = ("id", "tag", "region", "alt", "prompt", "model", "seed", "date", "host", "licence", "label", "web", "stream", "judge_notes", "corner_check")
TAGS = {"earthquake", "wildfire", "storm", "flood", "volcano", "heat", "winter", "outage", "conflict", "markets", "space", "cyber", "recall", "world", "region", "city"}


class StockBuild(unittest.TestCase):
    @unittest.skipIf(build_stock is None, 'no Pillow')
    def test_build_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "raw.png"); Image.new("RGB", (1920, 1088), (13, 23, 34)).save(raw)
            build_stock.OUT = os.path.join(d, "stock")
            m = build_stock.build({"earthquake-1": {"raw": raw, "tag": "earthquake", "alt": "x" * 200, "prompt": "p", "seed": 1}})
            self.assertEqual(len(m), 1)
            self.assertLessEqual(len(m[0]["alt"]), 125)
            self.assertEqual(m[0]["label"], "Illustration")
            for f in m[0]["web"] + [m[0]["stream"]]:
                self.assertTrue(os.path.exists(os.path.join(build_stock.OUT, f)), f)
            self.assertEqual(Image.open(os.path.join(build_stock.OUT, m[0]["stream"])).size, (1920, 1080))


class StockManifest(unittest.TestCase):
    def test_manifest_if_present(self):
        p = os.path.join(ROOT, "assets", "stock", "manifest.json")
        if not os.path.exists(p):
            self.skipTest("no manifest yet")
        items = json.load(open(p))["items"]
        for i in items:
            for k in FIELDS:
                self.assertIn(k, i)
            self.assertIn(i["tag"], TAGS)
            self.assertEqual(i["label"], "Illustration")
            self.assertTrue(i["licence"].startswith("generated in-house"))
            self.assertTrue(i["corner_check"], i["id"])
            self.assertLessEqual(len(i["alt"]), 125)
            for f in i["web"] + [i["stream"]]:
                self.assertTrue(os.path.exists(os.path.join(ROOT, "assets", "stock", f)), f)
            w1440 = [f for f in i["web"] if f.endswith("1440.avif")][0]
            self.assertLess(os.path.getsize(os.path.join(ROOT, "assets", "stock", w1440)), 150 * 1024)


if __name__ == "__main__":
    unittest.main()
