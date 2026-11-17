import ast
import os
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import manual_items, news_sweep as sweep, news_judge as judge, news_pending as pending
from tools.news_loop import run_once

FIX = Path(__file__).parent / 'fixtures'


class NewsPipelineTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 12, 5, tzinfo=timezone.utc)
        self.reply = (FIX / 'news-sweep-nsa.json').read_text()
        self.verdict_text = (FIX / 'judge-nsa.json').read_text()
        self.c = sweep.parse_candidates(self.reply)[0]
        self.v = judge.parse_verdict(self.verdict_text)

    def gate(self, c=None, v=None, live=()):
        return judge.gates(c or self.c, v or self.v, live, self.now)

    def test_replay(self):
        with tempfile.TemporaryDirectory() as d:
            result = run_once(self.now, lambda p: self.reply, lambda p: self.verdict_text,
                              Path(d)/'ledger.json', d, [])
            self.assertEqual(result, dict(found=1, published=1, held=0, rejected=0))
            item = json.loads((Path(d)/'auto_items.json').read_text())[0]
            self.assertEqual(manual_items.validate(item), [])
            self.assertEqual(len(item['sources']), 2)
            self.assertEqual(len(item['carried_by']), 3)
            self.assertNotIn('label', item)
            self.assertEqual(item['sources'][0]['source'], 'CNN')

    def test_one_source_held(self):
        self.c['outlets'] = self.c['outlets'][:1]
        self.assertFalse(self.gate()[0])
        with tempfile.TemporaryDirectory() as d:
            reply = json.dumps({'candidates':[self.c]})
            r = run_once(self.now, lambda p: reply, lambda p: self.verdict_text, Path(d)/'l.json', d, [])
            self.assertEqual(r['held'], 1)
            self.assertEqual(json.loads((Path(d)/'auto_items.json').read_text()), [])

    def test_carrying_and_sister_origins(self):
        for o in self.c['outlets']:
            o.update(role='carrying', own_sources=False)
        self.assertEqual(judge.origin_groups(self.c), set())
        self.assertFalse(judge.meets_bar(self.c)[0])
        self.c['outlets'] = [dict(name=d, url='https://'+d+'/a', role='original', own_sources=True) for d in ('wftv.com','wsoctv.com')]
        self.assertFalse(judge.meets_bar(self.c)[0])

    def test_editorial_gates(self):
        self.c['official_response'] = []
        self.assertIn('missing official response', self.gate()[1])
        self.setUp()
        self.v['headline'] = 'CNN reports terrifying interruption'
        self.assertFalse(self.gate()[0])
        self.setUp()
        self.v['headline'] = self.c['outlets'][0]['title']
        self.assertFalse(self.gate()[0])
        self.setUp()
        item = self.gate()[2]
        self.assertFalse(self.gate(live=[item])[0])
        self.assertFalse(self.gate(live=[dict(title=self.v['headline'],sources=[])])[0])

    def test_prompts_and_runners(self):
        self.assertNotEqual(sweep.build_prompt('x', 'now'), judge.judge_prompt(self.c))
        self.assertNotEqual(judge.SWEEP_MODEL, judge.JUDGE_MODEL)
        with patch('subprocess.run') as run:
            run.return_value.stdout = 'reply'
            sweep.default_runner('sweep')
            a = run.call_args
            judge.default_judge_runner('judge')
            b = run.call_args
        self.assertEqual(a.args[0][a.args[0].index('-m')+1], judge.SWEEP_MODEL)
        self.assertEqual(b.args[0][b.args[0].index('-m')+1], judge.JUDGE_MODEL)
        self.assertIn('-w', a.args[0])
        self.assertNotIn('-w', b.args[0])
        self.assertEqual((a.kwargs['timeout'], b.kwargs['timeout']), (600,300))

    def test_parallel(self):
        barrier = threading.Barrier(5)
        def runner(prompt):
            barrier.wait(timeout=5)
            return self.reply
        self.assertEqual(len(sweep.run_sweep(runner, self.now)), 5)

    def test_parser(self):
        payload = json.dumps({'candidates':[self.c]})
        self.assertEqual(len(sweep.parse_candidates('leading\n```json\n'+payload+'\n```')), 1)
        for url in ('http://cnn.com/a', 'https://invented.example/a', 'made-up', 'https://<guess>/a'):
            c = copy.deepcopy(self.c)
            c['outlets'] = [dict(c['outlets'][0], url=url)]
            self.assertEqual(sweep.parse_candidates(json.dumps({'candidates':[c]})), [])
        self.assertEqual(len(sweep.parse_candidates(json.dumps({'candidates':[self.c]*20}))), 12)
        self.assertIsNone(judge.parse_verdict('{}'))

    def test_dedupe_bridge(self):
        a, b, c = [copy.deepcopy(self.c) for _ in range(3)]
        a['outlets'] = self.c['outlets'][:1]
        b['outlets'] = self.c['outlets'][1:2]
        c['outlets'] = self.c['outlets'][:2]
        self.assertEqual(len(sweep.dedupe([a,b,c])), 1)

    def test_pending_and_hourly(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'ledger.json'
            pending.record(p, 'a', 'found', self.now)
            pending.record(p, 'a', 'held', self.now, 'needs sources')
            pending.record(p, 'b', 'found', self.now)
            pending.record(p, 'b', 'published', self.now)
            pending.record(p, 'c', 'found', self.now)
            pending.record(p, 'c', 'rejected', self.now)
            self.assertEqual(pending.pending_over(p, self.now+timedelta(minutes=9)), [])
            later = self.now+timedelta(minutes=10)
            self.assertEqual(pending.pending_over(p, later), ['a'])
            self.assertEqual(len(pending.alert_lines(p, later)), 1)
            self.assertEqual(pending.alert_lines(p, later), [])
            self.assertEqual(pending.hourly_line(p, later), '12:15 UTC hourly: found 3, published 1, held 1, rejected 1. Held: a: needs sources')
            self.assertIn('found 0', pending.hourly_line(p, later+timedelta(hours=2)))

    def test_unsupported_no_comment(self):
        self.c['official_response'] = []
        self.v['responses'] = [dict(who='NSA', text='has not commented')]
        self.assertFalse(self.gate()[0])

    def test_push_disabled(self):
        with self.assertRaisesRegex(NotImplementedError, 'guarded wrapper'):
            run_once(self.now, None, None, None, None, [], push=True)

    def test_no_cloud_clients(self):
        for p in (Path(__file__).parents[1]/'tools').glob('news_*.py'):
            tree = ast.parse(p.read_text())
            for node in ast.walk(tree):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse({'anthropic','openai','google','requests'} & {m.split('.')[0] for m in modules}, str(p))


class PublishIsGated(unittest.TestCase):
    def test_publish_does_nothing_without_the_approval_file(self):
        import tempfile
        from tools import news_loop
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "auto_items.json"), "w").write("[]")
            self.assertEqual(news_loop.publish(d), "dry: PUSH_APPROVED missing")
            self.assertFalse(os.path.exists(os.path.join(d, "news-data-clone")))

    def test_the_default_output_folder_is_outside_the_repo(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "news_loop.py"), encoding="utf-8").read()
        self.assertIn("factory-scratch", src)
        self.assertNotIn("'news_output'", src)


class ConfirmationSearch(unittest.TestCase):
    """A story with one own-sourced origin gets ONE confirmation search, then one more judgement."""

    def test_a_confirming_outlet_found_by_the_second_search_lets_the_story_publish(self):
        import tempfile
        now = datetime(2026, 11, 17, 18, 30, tzinfo=timezone.utc)
        first = json.dumps({"candidates": [{"beat": "Tech, outages and cyber", "what_happened": "CNN reports the NSA classified network is down.", "first_seen_utc": "2026-11-17T16:15:00Z", "scope": "six people familiar",
                                            "outlets": [{"name": "CNN", "url": "https://www.cnn.com/2026/11/17/us/nsa-net", "role": "original", "own_sources": True, "sourcing": "six people familiar"}],
                                            "official_response": [], "notes": ""}]})
        confirm = json.dumps({"outlets": [{"name": "CBS News", "url": "https://www.cbsnews.com/news/nsa-network-down-classified-fort-meade/", "role": "confirming", "own_sources": True, "sourcing": "two US officials spoke to CBS News"}],
                              "official_response": [{"who": "NSA", "text": "has not commented in the reports", "url": "https://www.cbsnews.com/news/nsa-network-down-classified-fort-meade/"}]})
        verdict = json.dumps({"decision": "publish", "reasons": [], "headline": "CNN and CBS report the NSA's classified network is down; the NSA has not commented in the reports",
                              "summary": "CNN reported, citing six people familiar, that the NSA's classified network is down. CBS News, citing US officials, reports the same. The desk has not confirmed it.",
                              "responses": [{"who": "NSA", "text": "has not commented in the reports"}]})
        calls = []

        def sweep(prompt):
            calls.append(prompt[:40])
            return confirm if "OTHER major outlets" in prompt else (first if "Tech, outages" in prompt else json.dumps({"candidates": []}))
        with tempfile.TemporaryDirectory() as d:
            counts = run_once(now, sweep, lambda p: verdict, os.path.join(d, "ledger.json"), d, [])
            items = json.load(open(os.path.join(d, "auto_items.json")))
        self.assertEqual(counts["published"], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(items[0]["sources"]), 2)
        self.assertEqual(sum(1 for c in calls if c.startswith("Web-search task. Now:")), 1)       # exactly one confirmation search

    def test_without_a_confirming_outlet_the_story_stays_held(self):
        import tempfile
        now = datetime(2026, 11, 17, 18, 30, tzinfo=timezone.utc)
        first = json.dumps({"candidates": [{"beat": "Tech, outages and cyber", "what_happened": "CNN reports the NSA classified network is down.", "first_seen_utc": "2026-11-17T16:15:00Z", "scope": "six people familiar",
                                            "outlets": [{"name": "CNN", "url": "https://www.cnn.com/2026/11/17/us/nsa-net", "role": "original", "own_sources": True, "sourcing": "six people familiar"}],
                                            "official_response": [], "notes": ""}]})
        verdict = json.dumps({"decision": "hold", "reasons": ["only one origin"], "headline": "x", "summary": "x. The desk has not confirmed it.", "responses": []})
        sweep = lambda prompt: json.dumps({"outlets": [], "official_response": []}) if "OTHER major outlets" in prompt else (first if "Tech, outages" in prompt else json.dumps({"candidates": []}))
        with tempfile.TemporaryDirectory() as d:
            counts = run_once(now, sweep, lambda p: verdict, os.path.join(d, "ledger.json"), d, [])
        self.assertEqual(counts["published"], 0)
        self.assertEqual(counts["held"], 1)


class ConfirmationRunsWhenTheJudgeHolds(unittest.TestCase):
    def test_a_judge_hold_for_one_origin_still_gets_the_confirmation_search(self):
        import tempfile
        now = datetime(2026, 11, 17, 18, 30, tzinfo=timezone.utc)
        first = json.dumps({"candidates": [{"beat": "Tech, outages and cyber", "what_happened": "CNN reports the NSA classified network is down.", "first_seen_utc": "2026-11-17T16:15:00Z", "scope": "six people familiar",
                                            "outlets": [{"name": "CNN", "url": "https://www.cnn.com/2026/11/17/us/nsa-net", "role": "original", "own_sources": True, "sourcing": "six people familiar"}],
                                            "official_response": [], "notes": ""}]})
        asked = []

        def sweep(prompt):
            if "OTHER major outlets" in prompt:
                asked.append(1)
                return json.dumps({"outlets": [], "official_response": []})
            return first if "Tech, outages" in prompt else json.dumps({"candidates": []})
        hold = json.dumps({"decision": "hold", "reasons": ["only one origin"], "headline": "x", "summary": "x. The desk has not confirmed it.", "responses": []})
        with tempfile.TemporaryDirectory() as d:
            run_once(now, sweep, lambda p: hold, os.path.join(d, "ledger.json"), d, [])
        self.assertEqual(len(asked), 1)


class LiveItems(unittest.TestCase):
    def test_live_events_become_duplicate_gate_input(self):
        from tools import news_loop
        live = news_loop.live_items_from_events([{"title": "CNN and CBS report NSA's classified internal network is down", "source_url": "https://www.cnn.com/x",
                                                   "links": [{"url": "https://www.cbsnews.com/news/nsa-network-down-classified-fort-meade/"}]}])
        self.assertEqual(live[0]["sources"][0]["url"], "https://www.cnn.com/x")
        self.assertEqual(live[0]["links"][0]["url"], "https://www.cbsnews.com/news/nsa-network-down-classified-fort-meade/")

    def test_a_failed_fetch_gives_no_live_items(self):
        from tools import news_loop
        def boom(url, timeout=0):
            raise OSError("down")
        self.assertEqual(news_loop.load_live_items(opener=boom), [])
