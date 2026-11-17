"""Static news pages, using fictional desk copy and example sources only."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import news_pages as news, build_data

NOW = datetime(2026, 11, 17, 15, tzinfo=timezone.utc)


def event(**changes):
    item = {"id": "desk-1", "title": "Agency reports a service review in DC", "place": "DC",
            "time": "2026-11-17T12:00:00Z", "summary": "Example Agency says a service review is underway.",
            "confidence": "Unverified lead", "detail": {
                "reported_line": "Reported by Example Wire", "sources": [{"source": "Example Wire"}],
                "responses": [{"who": "Example Agency", "text": "A review is underway."}],
                "expires": "2026-11-18T12:00:00Z"},
            "links": [{"label": "Example Wire", "url": "https://wire.example/review?a=1&b=2",
                       "title": "OUTLET HEADLINE MUST NOT APPEAR"}]}
    item.update(changes)
    return item


class NewsPages(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(news.slugify("Café & DC: Review!"), "cafe-dc-review")
        self.assertLessEqual(len(news.slugify("word " * 40)), 60)
        self.assertEqual(news.slugify("!!!"), "news")
        self.assertTrue(news.slugify("中文").isascii())

    def test_html_and_json_escaping_and_metadata(self):
        hostile = '<script>alert("x")</script> & review'
        item = event(title=hostile, summary=hostile, place=hostile)
        item["detail"]["reported_line"] = hostile
        item["detail"]["responses"][0]["text"] = hostile
        page = news.render_page(item, NOW)
        self.assertNotIn('<script>alert', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('href="/tokens.css"', page)
        self.assertIn('href="/style.css"', page)
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
        self.assertEqual(len(blocks), 1)
        data = json.loads(blocks[0])
        self.assertEqual(data["@type"], "NewsArticle")
        self.assertEqual(data["headline"], hostile)
        self.assertEqual(data["publisher"], {"@type": "Organization", "name": "Breaking News Desk"})
        self.assertNotIn("author", data)
        self.assertEqual(data["isBasedOn"], [item["links"][0]["url"]])
        url = news.BASE + '/news/desk-1/' + news.slugify(hostile) + '/'
        self.assertIn('<link rel="canonical" href="' + url + '">', page)
        self.assertEqual(data["mainEntityOfPage"], url)
        self.assertIn('rel="nofollow noopener"', page)
        self.assertNotIn("OUTLET HEADLINE MUST NOT APPEAR", page)

    def test_unsafe_source_url_is_not_linked(self):
        item = event()
        item["links"][0]["url"] = "javascript:alert(1)"
        self.assertNotIn("javascript:", news.render_page(item, NOW))

    def test_expired_and_withdrawn(self):
        item = event()
        item["detail"]["expires"] = "2026-11-17T13:00:00Z"
        self.assertIn("No longer in the live feed", news.render_page(item, NOW))
        self.assertNotIn('content="noindex"', news.render_page(item, NOW))
        item["confidence"] = "Corrected"  # Corrected stays public and indexable
        self.assertNotIn('content="noindex"', news.render_page(item, NOW))

    def test_sitemaps_and_retained_pages(self):
        stamp = lambda hours: (NOW - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
        items = [event(), event(id="boundary", time=stamp(48)), event(id="old", time=stamp(49)),
                 event(id="future", time=stamp(-1)), event(id="withdrawn", withdrawn=True, confidence="Corrected")]
        expired = event(id="expired", time=stamp(72))
        with tempfile.TemporaryDirectory() as out:
            urls = news.build_news(items + [{"id": "not-news"}], [expired], out, NOW)
            self.assertEqual(len(urls), 6)
            path = Path(out) / news._path(expired) / 'index.html'
            self.assertIn("No longer in the live feed", path.read_text())
            ns = {'s': news.SITEMAP, 'n': news.NEWS}
            tree = ET.parse(Path(out) / 'news-sitemap.xml')
            locs = [e.text for e in tree.findall('s:url/s:loc', ns)]
            self.assertEqual(len(locs), 2)
            self.assertTrue(any('/boundary/' in u for u in locs))
            self.assertEqual(len(tree.findall('s:url/n:news/n:publication/n:name', ns)), 2)
            pages = ET.parse(Path(out) / 'news-pages.xml')
            self.assertEqual(len(pages.findall('s:url/s:lastmod', ns)), 5)  # the corrected item has a page but is not in this sitemap
            saved = json.loads((Path(out) / 'news/events.json').read_text())
            news.build_news([], saved, out, NOW + timedelta(days=4))
            self.assertTrue(path.exists())

    def test_corrected_stays_public_and_withdrawn_flag_becomes_a_notice(self):
        with tempfile.TemporaryDirectory() as d:
            news.build_news([event(confidence="Corrected")], [], d, NOW)
            page = next(Path(d, "news").rglob("index.html")).read_text()
            self.assertNotIn('content="noindex"', page)
            self.assertIn("desk-1", Path(d, "news-sitemap.xml").read_text())
        with tempfile.TemporaryDirectory() as d:
            news.build_news([event(withdrawn=True)], [], d, NOW)
            page = next(Path(d, "news").rglob("index.html")).read_text()
            self.assertIn('content="noindex"', page)
            self.assertNotIn("service review is underway", page)
            self.assertNotIn("desk-1", Path(d, "news-sitemap.xml").read_text())

    def test_malformed_source_url_does_not_crash(self):
        e = event()
        e["detail"] = dict(e["detail"], sources=[{"source": "Bad", "url": "https://[invalid"}])
        self.assertIn("Bad", news.render_page(e, NOW))

    def test_title_change_removes_the_old_page(self):
        with tempfile.TemporaryDirectory() as d:
            news.build_news([event()], [], d, NOW)
            news.build_news([event(title="A different title", confidence="Corrected")], [], d, NOW)
            pages = list(Path(d, "news", "desk-1").glob("*/index.html"))
            self.assertEqual(len(pages), 1)
            self.assertIn("a-different-title", str(pages[0]))
            self.assertNotIn("agency-reports", Path(d, "news-pages.xml").read_text())

    def test_dotted_id_and_null_history_are_safe(self):
        with tempfile.TemporaryDirectory() as d:
            urls = news.build_news([event(id="desk.1", history=None)], [], d, NOW)
            self.assertEqual(len(urls), 1)
            self.assertTrue((Path(d) / urls[0].replace(news.BASE + "/", "") / "index.html").exists())

    def test_pulled_item_becomes_a_notice_with_no_body_and_no_sitemap_entry(self):
        with tempfile.TemporaryDirectory() as d:
            news.build_news([event(), event(id="keep", title="Other item")], [], d, NOW)
            archived = json.loads(Path(d, "news", "events.json").read_text())
            news.build_news([], archived, d, NOW, withdrawn={"desk-1": {"date": "2026-11-17", "reason": "date was wrong"}})
            page = next(Path(d, "news", "desk-1").rglob("index.html")).read_text()
            self.assertIn("withdrawn on 2026-11-17: date was wrong", page)
            self.assertIn('content="noindex"', page)
            self.assertNotIn("service review is underway", page)  # no article body
            self.assertNotIn("Example Wire", page)
            for name in ("news-pages.xml", "news-sitemap.xml"):
                self.assertNotIn("desk-1", Path(d, name).read_text())
            self.assertIn("keep", Path(d, "news-pages.xml").read_text())
            # a later build from the archive keeps the notice
            news.build_news([], json.loads(Path(d, "news", "events.json").read_text()), d, NOW, withdrawn={"desk-1": {"date": "2026-11-17", "reason": "date was wrong"}})
            self.assertTrue(next(Path(d, "news", "desk-1").rglob("index.html")).exists())

    def test_dotted_and_dashed_ids_do_not_collide(self):
        self.assertNotEqual(news._path(event(id="desk.1")), news._path(event(id="desk-1")))

    def test_changed_since(self):
        item = event()
        self.assertEqual(news.changed_since(item), 'No changes since first published at 12:00 UTC.')
        item['updated'] = '2026-11-17T14:05:00Z'
        self.assertEqual(news.changed_since(item), 'Updated 14:05 UTC: item updated')
        item['history'] = [{'t': item['updated'], 'from': 'Unverified lead', 'to': 'Corroborated'}]
        self.assertEqual(news.changed_since(item), 'Updated 14:05 UTC: label raised from Unverified lead to Corroborated')
        item['history'][0].update({'from': 'Corroborated', 'to': 'Unverified lead'})
        self.assertIn('label lowered', news.changed_since(item))
        item['history'][0].update({'to': 'Corrected'})
        self.assertIn('label changed', news.changed_since(item))
        item['history'][0].update({'from': 'Corrected', 'why': 'Example Agency revised its statement'})
        self.assertIn('Example Agency revised its statement', news.changed_since(item))
        page = news.render_page(item, NOW)
        self.assertIn('"dateModified": "2026-11-17T14:05:00Z"', page)

    def test_freshness(self):
        rows = [{'name': 'Example %s' % n, 'missed': n} for n in range(5)]
        result = news.source_freshness({'sources': rows}, NOW)
        self.assertEqual([r['state'] for r in result], ['fresh', 'fresh', 'fresh', 'stale', 'stale'])
        result = news.source_freshness({'sources': [{'name': 'Example', 'checked': '2026-11-17T14:30:00Z', 'ok': True}]}, NOW)
        self.assertEqual(result, [{'name': 'Example', 'state': 'stale', 'missed': 3}])

    def test_main_without_flag_writes_no_news(self):
        with tempfile.TemporaryDirectory() as out:
            with patch.object(build_data, 'build', return_value=([event()], [])), patch.object(build_data.killswitch, 'global_stop', return_value=False), patch.object(build_data, 'track_seen'), patch.object(build_data.lead_story, 'build', return_value={}), patch.object(sys, 'argv', ['build_data', '--fixtures', out, '--out', out]):
                self.assertEqual(build_data.main(), 0)
            self.assertFalse((Path(out) / 'news').exists())
            self.assertFalse((Path(out) / 'news-pages.xml').exists())

    def test_main_flag_and_archive(self):
        with tempfile.TemporaryDirectory() as out:
            item = event()
            with patch.object(build_data, 'build', return_value=([item], [])), patch.object(build_data.killswitch, 'global_stop', return_value=False), patch.object(build_data, 'track_seen'), patch.object(build_data.lead_story, 'build', return_value={}), patch.object(sys, 'argv', ['build_data', '--fixtures', out, '--out', out, '--news-pages']):
                self.assertEqual(build_data.main(), 0)
            self.assertTrue((Path(out) / 'news-pages.xml').exists())
            other = event(id='desk-2')
            with patch.object(build_data, 'build', return_value=([other], [])), patch.object(build_data.killswitch, 'global_stop', return_value=False), patch.object(build_data, 'track_seen'), patch.object(build_data.lead_story, 'build', return_value={}), patch.object(sys, 'argv', ['build_data', '--fixtures', out, '--out', out, '--news-pages']):
                build_data.main()
            page = Path(out) / news._path(item) / 'index.html'
            self.assertIn('No longer in the live feed', page.read_text())


if __name__ == '__main__':
    unittest.main()
