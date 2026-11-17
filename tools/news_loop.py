"""Local-only sweep and judge loop. Publication here means a local JSON artifact."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

from tools import news_pending as ledger
from tools.lib import parse_time
from tools.news_sweep import run_sweep, dedupe, default_runner, confirm_prompt, merge_confirmation
from tools.news_judge import candidate_id, judge_prompt, parse_verdict, gates, default_judge_runner, meets_bar


def read_lines(path):
    """Whitespace-separated words of a control file. A missing file is empty; any other read error raises (fail closed)."""
    try:
        return Path(path).read_text().split()
    except FileNotFoundError:
        return []


def run_once(now, sweep_runner, judge_runner, ledger_path, out_dir, live_items, push=False, hold=None):
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
    blocked = set(read_lines(Path(out_dir) / 'blocklist.txt'))
    candidates = dedupe(run_sweep(sweep_runner, now))
    for c in candidates:
        if hold and hold():
            break
        cid = candidate_id(c)
        if cid in blocked:
            continue
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
        if ok and hold and hold():
            ok, reasons = False, ['HOLD file present']
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


def control_dir():
    return Path.home() / 'factory-scratch' / 'bnd'


def read_pull(path):
    """Ids to pull, one per line ('id' or 'id | note')."""
    out = {}
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            cid, _, note = line.partition('|')
            out[cid.strip()] = note.strip()
    return out


def apply_pulls(out_dir, pull_path, ledger_path, now):
    """Correction path: remove pulled ids from auto_items.json within one cycle, remember them, log the correction."""
    pulls = read_pull(pull_path)
    if not pulls:
        return []
    out = Path(out_dir)
    try:
        known = set(read_lines(out / 'blocklist.txt'))
    except (OSError, ValueError):
        known = set()  # an unreadable blocklist never blocks a takedown; the ids are appended again
    new_ids = [cid for cid in pulls if cid not in known]
    if new_ids:  # block first, so a failure after this line can only over-block
        try:
            with (out / 'blocklist.txt').open('a') as f:
                f.write('\n' + '\n'.join(new_ids) + '\n')
        except OSError:
            pass  # the takedown below still runs; the PULL file itself keeps blocking in publish
    path = out / 'auto_items.json'
    items = ledger.read(path) if path.exists() else []
    pulled = [i['id'] for i in items if i.get('id') in pulls]
    if pulled:
        ledger.write(path, [i for i in items if i.get('id') not in pulls])
        with (out / 'corrections.log').open('a') as f:
            for cid in pulled:
                f.write('%s pulled %s\n' % (now.strftime('%Y-%m-%dT%H:%M:%SZ'), cid))
                ledger.record(ledger_path, cid, 'answered', now, 'pulled')
    return pulled


def new_published_lines(items, seen_path):
    """(lines, ids) for items not yet marked seen: headline and source names only."""
    seen = set(read_lines(seen_path))
    lines, ids = [], []
    for i in items:
        if i['id'] not in seen:
            ids.append(i['id'])
            lines.append('%s | %s | sources: %s' % (i['id'], i['title'], '; '.join(s['source'] + ' ' + s['url'] for s in i['sources'])))
    return lines, ids


def log_published(out_dir, items, seen_path, pushed):
    """Write the lines for new items to published.md and mark them seen, only after a successful push."""
    lines, ids = new_published_lines(items, seen_path)
    if lines and pushed:
        with (Path(out_dir) / 'published.md').open('a') as f:
            f.write('\n'.join(lines) + '\n')
        Path(seen_path).write_text('\n'.join(sorted(set(read_lines(seen_path)) | set(ids))))
        return lines
    return []


def publish(out_dir, clone_url=None, removals_only=False):
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
    # The remote branch is the baseline: drop any unpushed local commit or edit left by a failed earlier push.
    fetched = subprocess.run(['git', '-C', str(clone), 'fetch', '-q', 'origin', 'news-data'], capture_output=True, timeout=90)
    if fetched.returncode == 0:
        subprocess.run(['git', '-C', str(clone), 'reset', '-q', '--hard', 'FETCH_HEAD'], check=True)
    else:
        ls = subprocess.run(['git', '-C', str(clone), 'ls-remote', '--heads', 'origin', 'news-data'], capture_output=True, text=True, timeout=60)
        if ls.returncode != 0 or ls.stdout.strip():
            return 'held: cannot read the remote'  # unreachable, or the branch exists but the fetch failed
        # rc 0 and no heads: the branch does not exist yet, so this is the first push
        if removals_only or (control_dir() / 'HOLD').exists():
            return 'held: no live branch yet, nothing to take down'
        subprocess.run(['git', '-C', str(clone), 'update-ref', '-d', 'HEAD'], capture_output=True)  # drop any failed first commit; the file is copied fresh below
    if (control_dir() / 'HOLD').exists():  # HOLD may arrive during the fetch
        removals_only = True
    if not removals_only:
        shutil.copy(out / 'auto_items.json', clone / 'auto_items.json')
    elif not (clone / 'auto_items.json').exists():
        return 'held: no live file to take down from'
    late = set(read_pull(control_dir() / 'PULL'))  # a pull that arrived during the fetch still wins
    try:
        late |= set(read_lines(out / 'blocklist.txt'))  # a blocked id never goes back live
    except (OSError, ValueError):
        pass
    if late:
        ledger.write(clone / 'auto_items.json', [i for i in ledger.read(clone / 'auto_items.json') if i['id'] not in late])
        if (out / 'auto_items.json').exists():
            ledger.write(out / 'auto_items.json', [i for i in ledger.read(out / 'auto_items.json') if i['id'] not in late])
    git = ['git', '-C', str(clone), '-c', 'user.name=Zuggary', '-c', 'user.email=Zuggary@users.noreply.github.com']
    subprocess.run(git + ['add', 'auto_items.json'], check=True)
    if subprocess.run(git + ['diff', '--cached', '--quiet']).returncode == 0:
        return 'no change'
    subprocess.run(git + ['commit', '-q', '-m', 'auto items'], check=True)
    if not removals_only and (control_dir() / 'HOLD').exists():
        return 'held: HOLD arrived before the push'  # the local commit is dropped by the next fetch and reset
    subprocess.run(git + ['push', '-q', 'origin', 'HEAD:news-data'], check=True, timeout=120)
    return 'pushed'


def cycle(now, ledger_path, out, do_publish, sweep_runner=default_runner, judge_runner=default_judge_runner, live=None, cdir=None):
    """One loop pass. Pulls first. HOLD stops new items only; removals still push. A control-file error stops new items and returns an alert line."""
    cdir = Path(cdir) if cdir else control_dir()
    out = Path(out)
    alert = None
    try:
        apply_pulls(out, cdir / 'PULL', ledger_path, now)
        read_lines(out / 'blocklist.txt')
        if not (cdir / 'HOLD').exists():
            run_once(now, sweep_runner, judge_runner, ledger_path, out, load_live_items() if live is None else live,
                     hold=lambda: (cdir / 'HOLD').exists())
        apply_pulls(out, cdir / 'PULL', ledger_path, now)  # again, in case a pull arrived while the sweep ran
    except Exception as exc:  # noqa: BLE001  fail closed: no new items this cycle
        alert = '%s ALERT: control files or sweep failed, no new items: %s' % (now.strftime('%Y-%m-%dT%H:%M:%SZ'), exc)
    # After an alert or under HOLD only removals go out; new items never do.
    removals_only = bool(alert) or (cdir / 'HOLD').exists()
    try:
        result = publish(out, removals_only=removals_only) if do_publish else 'dry'
    except Exception as exc:  # noqa: BLE001
        result, alert = 'alert: publish failed', '%s ALERT: publish failed: %s' % (now.strftime('%Y-%m-%dT%H:%M:%SZ'), exc)
    try:
        if (out / 'news-data-clone' / 'auto_items.json').exists() and result in ('pushed', 'no change'):
            log_published(out, ledger.read(out / 'news-data-clone' / 'auto_items.json'), out / 'published.seen', True)
    except Exception as exc:  # noqa: BLE001  a log failure never stops takedowns
        alert = alert or '%s ALERT: published log failed: %s' % (now.strftime('%Y-%m-%dT%H:%M:%SZ'), exc)
    return alert


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
        try:
            status = cycle(now, path, out, args.publish)
        except Exception as exc:  # noqa: BLE001  nothing may stop the loop
            status = 'ALERT: cycle failed: %s' % exc
        lines = ([status] if status else [])
        try:
            lines += ledger.alert_lines(path, now)
            hour = now.strftime('%Y-%m-%dT%H')
            hourly = ledger.hourly_line(path, now) if hour != last_hour else None
            last_hour = hour
        except Exception as exc:  # noqa: BLE001
            lines.append('ALERT: ledger failed: %s' % exc)
            hourly = None
        for name, text in (('ALERTS.md', lines), ('hourly.md', [hourly] if hourly else [])):
            if text:
                try:
                    with (out / name).open('a') as f:
                        f.write('\n'.join(text) + '\n')
                except OSError:
                    pass
        if args.once:
            return
        time.sleep(args.every)


if __name__ == '__main__':
    main()
