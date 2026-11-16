"""Clean URLs: no internal link ends in .html, and every clean internal URL returns 200 on a server that behaves like GitHub Pages
(a path with no extension is served from path.html; "/" is index.html)."""
import http.server
import os
import re
import threading
import unittest
import urllib.request
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://breakingnewsdesklive.com"
PAGES = ("about", "privacy", "data", "corrections", "event", "tv")


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def sources():
    names = [f for f in os.listdir(ROOT) if f.endswith(".html")] + ["app.js", "lib.js", "sw.js", "sitemap.xml"]
    return {n: read(n) for n in names}


def internal_refs():
    """Every internal link target found in the html and the page scripts."""
    refs = set()
    for name, text in sources().items():
        for m in re.finditer(r'href="([^"]+)"', text):
            refs.add(m.group(1))
        for m in re.finditer(r"""(?:href|ca\.href|pl\.href|l\.href|ta\.href)\s*=\s*['"]([^'"]+)['"]""", text):
            refs.add(m.group(1))
        for m in re.finditer(r"<loc>([^<]+)</loc>", text):
            refs.add(m.group(1))
        for m in re.finditer(r'(?:canonical|og:url)[^>]*(?:href|content)="([^"]+)"', text):
            refs.add(m.group(1))
    out = set()
    for r in refs:
        if r.startswith(SITE):
            r = r[len(SITE):] or "/"
        if re.match(r"^(https?:|mailto:|data:|javascript:|#|//)", r):
            continue
        out.add(r)
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            f = "index.html"
        elif "." not in os.path.basename(path):
            f = path.strip("/") + ".html"
        else:
            f = path.strip("/")
        full = os.path.join(ROOT, f)
        if os.path.isfile(full):
            self.send_response(200); self.end_headers(); self.wfile.write(open(full, "rb").read())
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a):
        pass


class CleanUrls(unittest.TestCase):
    def test_no_internal_href_ends_in_html(self):
        bad = sorted(r for r in internal_refs() if re.search(r"\.html(?:$|[?#])", r))
        self.assertEqual(bad, [])

    def test_no_html_extension_in_page_sources(self):
        pat = re.compile(r"(?<![\w/.:-])(?:\./)?(?:%s|index)\.html" % "|".join(PAGES))
        offenders = {n: pat.findall(t) for n, t in sources().items() if pat.search(t)}
        self.assertEqual(offenders, {})
        own = re.compile(r"breakingnewsdesklive\.com/(?:%s|index)\.html" % "|".join(PAGES))
        self.assertEqual({n: 1 for n, t in sources().items() if own.search(t)}, {})

    def test_canonicals_ogurls_and_sitemap_are_clean(self):
        for name in ("index.html", "about.html", "privacy.html", "data.html", "corrections.html"):
            t = read(name)
            for rx in (r'rel="canonical" href="([^"]+)"', r'property="og:url" content="([^"]+)"'):
                m = re.search(rx, t)
                self.assertTrue(m, (name, rx))
                self.assertFalse(m.group(1).endswith(".html"), m.group(1))
        locs = re.findall(r"<loc>([^<]+)</loc>", read("sitemap.xml"))
        self.assertGreaterEqual(len(locs), 5)
        for l in locs:
            self.assertNotIn(".html", l)

    def test_every_clean_url_returns_200(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            refs = {r.split("#")[0] for r in internal_refs()}
            refs |= {"/", "/about", "/privacy", "/data", "/corrections", "/event", "/tv"}
            checked = 0
            for r in sorted(refs):
                if not r.startswith("/") and not r.startswith("./"):
                    continue
                url = "http://127.0.0.1:%d%s" % (srv.server_port, r[1:] if r.startswith("./") and r != "./" else ("/" if r == "./" else r))
                if "." in os.path.basename(urlsplit(url).path):   # assets such as style.css and favicon.svg: the file must exist
                    pass
                with urllib.request.urlopen(url, timeout=5) as resp:
                    self.assertEqual(resp.status, 200, url)
                checked += 1
            self.assertGreaterEqual(checked, 7)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
