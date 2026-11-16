"""Every local file that a CSS url() or an HTML src/href points at must be tracked by git, or the deploy 404s."""
import os, re, subprocess, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return set(out.split("\n"))


def local(ref):
    ref = ref.split("#")[0].split("?")[0].strip()
    if not ref or re.match(r"^(https?:|data:|mailto:|//|/|javascript:)", ref):
        return None
    return os.path.normpath(ref)


class TrackedAssets(unittest.TestCase):
    def test_css_and_html_refs_are_tracked(self):
        files = tracked()
        if files is None:
            self.skipTest("not a git checkout")
        missing = []
        for name in sorted(os.listdir(ROOT)):
            p = os.path.join(ROOT, name)
            if name.endswith(".css"):
                refs = re.findall(r"url\(\s*['\"]?([^'\")]+)", open(p, encoding="utf-8").read())
            elif name.endswith(".html"):
                refs = re.findall(r'(?:src|href)="([^"]+)"', open(p, encoding="utf-8").read())
            else:
                continue
            for r in refs:
                f = local(r)
                if f and os.path.splitext(f)[1] in (".woff2", ".woff", ".css", ".js", ".svg", ".png", ".jpg", ".webp", ".avif", ".json", ".ico") and f not in files:
                    missing.append("%s -> %s" % (name, f))
        self.assertEqual(missing, [], "files referenced but not tracked by git")


if __name__ == "__main__":
    unittest.main()
