"""Offline regressions for source validation and accessible page structure."""
from html.parser import HTMLParser
from pathlib import Path
import unittest
from tools import news_pages

ROOT = Path(__file__).resolve().parents[1]

class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs), tuple(self.stack)))
        if tag not in ('meta', 'link', 'img', 'input', 'br', 'hr', 'source'):
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]

class SweepFixes(unittest.TestCase):
    def test_source_requires_http_hostname_and_preserves_name(self):
        for url in ('https:', 'https:///missing', 'http://', 'https://[bad', 'javascript:alert(1)'):
            result = news_pages._sources({'links': [{'label': 'Example source', 'url': url}]})
            self.assertEqual(result, [('Example source', '')])
        self.assertEqual(news_pages._sources({'links': [{'label': 'Example source', 'url': 'https://source.example/story'}]}), [('Example source', 'https://source.example/story')])

    def test_event_heading_and_details_share_main(self):
        nodes = Elements((ROOT / 'event.html').read_text()).nodes
        for identity in ('etitle', 'ev'):
            node = next(n for n in nodes if n[1].get('id') == identity)
            self.assertIn('main', node[2])
        self.assertEqual(sum(n[0] == 'main' for n in nodes), 1)

    def test_skip_and_map_targets_accept_focus(self):
        nodes = Elements((ROOT / 'index.html').read_text()).nodes
        for identity in ('list-wrap', 'map-wrap'):
            self.assertEqual(next(n[1] for n in nodes if n[1].get('id') == identity)['tabindex'], '-1')

    def test_offline_cache_has_unique_files_and_excludes_counter(self):
        import json, re
        text = (ROOT / 'sw.js').read_text()
        paths = json.loads(re.search(r'var FILES = (\[.*?\]);', text, re.S)[1])
        self.assertEqual(len(paths), len(set(paths)))
        self.assertNotIn('./count.js', paths)
        self.assertIn('k.indexOf("bnd-offline-") === 0', text)
