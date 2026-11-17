"""Local-only sweep and judge loop. Publication here means a local JSON artifact."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

from tools import news_pending as ledger
from tools.lib import parse_time
from tools.news_sweep import run_sweep, dedupe, default_runner, confirm_prompt, merge_confirmation
from tools.news_judge import candidate_id, judge_prompt, parse_verdict, gates, default_judge_runner, meets_bar


def run_once(now, sweep_runner, judge_runner, ledger_path, out_dir, live_items, push=False):
    if push:
        raise NotImplementedError('push is done by the guarded wrapper')
    path = Path(out_dir) / 'auto_items.json'
    existing = ledger.read(path) if path.exists() else []
    active = []
    for item in existing:
        try:
            if parse_time(item['expires']) > now:
                active.append(item)
        except (KeyError, ValueError, TypeError):
            continue
    counts = dict(found=0, published=0, held=0, rejected=0)
    candidates = dedupe(run_sweep(sweep_runner, now))
    for c in candidates:
        cid = candidate_id(c)
        ledger.record(ledger_path, cid, 'found', now)
        counts['found'] += 1
        try:
            verdict = parse_verdict(judge_runner(judge_prompt(c)))
            ledger.record(ledger_path, cid, 'judged', now)
            ok, reasons, item = gates(c, verdict, list(live_items) + active, now)
            if not ok and not meets_bar(c)[0]:
                # One confirmation search for a story that has only one own-sourced origin. Then judge the merged story once.
                c2 = merge_confirmation(c, sweep_runner(confirm_prompt(c, now.strftime('%Y-%m-%dT%H:%M:%SZ'))))
                if c2 is not c and len(c2['outlets']) > len(c['outlets']):
                    new_id = candidate_id(c2)
                    ledger.record(ledger_path, cid, 'answered', now, 'merged into ' + new_id)
                    c, cid = c2, new_id
                    ledger.record(ledger_path, cid, 'found', now, 'after confirmation search')
                    verdict = parse_verdict(judge_runner(judge_prompt(c)))
                    ledger.record(ledger_path, cid, 'judged', now)
                    ok, reasons, item = gates(c, verdict, list(live_items) + active, now)
        except Exception as exc:
            verdict, ok, reasons, item = None, False, ['judge error: ' + str(exc)], None
            ledger.record(ledger_path, cid, 'judged', now, reasons[0])
        if ok:
            active.append(item)
            state = 'published'
        else:
            state = 'rejected' if verdict and verdict['decision'] == 'reject' else 'held'
        ledger.record(ledger_path, cid, state, now, '; '.join(reasons))
        counts[state] += 1
    active.sort(key=lambda item: item['time'])
    ledger.write(path, active[-10:])
    return counts


LIVE_EVENTS_URL = 'https://breakingnewsdesklive.com/data/events.json'


def live_items_from_events(events):
    """Shape live events like items for the duplicate gate: title plus every source and link URL."""
    out = []
    for e in events if isinstance(events, list) else []:
        d = e.get('detail') or {}
        out.append({'title': e.get('title', ''), 'sources': [{'url': e.get('source_url')}], 'links': [{'url': l.get('url')} for l in e.get('links', []) if isinstance(l, dict)]})
    return out


def load_live_items(url=LIVE_EVENTS_URL, opener=None):
    """The items now on the site, so a story that is already live is not published twice. An error returns []."""
    import json
    import urllib.request
    try:
        with (opener or urllib.request.urlopen)(url, timeout=30) as r:
            return live_items_from_events(json.load(r).get('events', []))
    except Exception:  # noqa: BLE001
        return []


def publish(out_dir, clone_url=None):
    """Push out_dir/auto_items.json to the data-only branch news-data. Runs only when the file PUSH_APPROVED exists in out_dir.
    That file is created by whoever added the standing approvals line for this exact push. Without it nothing is pushed (dry mode)."""
    import shutil
    import subprocess
    out = Path(out_dir)
    if not (out / 'PUSH_APPROVED').exists():
        return 'dry: PUSH_APPROVED missing'
    clone = out / 'news-data-clone'
    url = clone_url or 'https://github.com/Zuggary/breakingnewsdesklive.git'
    if not clone.exists():
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', 'news-data', url, str(clone)], check=False, capture_output=True)
        if not clone.exists():
            clone.mkdir(parents=True)
            subprocess.run(['git', '-C', str(clone), 'init', '-q', '-b', 'news-data'], check=True)
            subprocess.run(['git', '-C', str(clone), 'remote', 'add', 'origin', url], check=True)
    shutil.copy(out / 'auto_items.json', clone / 'auto_items.json')
    git = ['git', '-C', str(clone), '-c', 'user.name=Zuggary', '-c', 'user.email=Zuggary@users.noreply.github.com']
    subprocess.run(git + ['add', 'auto_items.json'], check=True)
    if subprocess.run(git + ['diff', '--cached', '--quiet']).returncode == 0:
        return 'no change'
    subprocess.run(git + ['commit', '-q', '-m', 'auto items'], check=True)
    subprocess.run(git + ['push', '-q', 'origin', 'HEAD:news-data'], check=True)
    return 'pushed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--every', type=float, default=900)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--dry', action='store_true', help='local artifacts only (also the default)')
    parser.add_argument('--out-dir', default=str(Path.home() / 'factory-scratch' / 'newsloop'))
    parser.add_argument('--publish', action='store_true', help='push auto_items.json to the news-data branch; needs the PUSH_APPROVED file in the out dir')
    parser.add_argument('--ledger', default=None)
    args = parser.parse_args()
    if args.every <= 0:
        parser.error('--every must be positive')
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = args.ledger or str(out / 'ledger.json')
    last_hour = None
    while True:
        now = datetime.now(timezone.utc)
        run_once(now, default_runner, default_judge_runner, path, out, load_live_items())
        if args.publish:
            publish(out)
        lines = ledger.alert_lines(path, now)
        out.mkdir(parents=True, exist_ok=True)
        if lines:
            with (out / 'ALERTS.md').open('a') as f:
                f.write('\n'.join(lines) + '\n')
        else:
            (out / 'ALERTS.md').touch(exist_ok=True)
        hour = now.strftime('%Y-%m-%dT%H')
        if hour != last_hour:
            with (out / 'hourly.md').open('a') as f:
                f.write(ledger.hourly_line(path, now) + '\n')
            last_hour = hour
        if args.once:
            return
        time.sleep(args.every)


if __name__ == '__main__':
    main()
