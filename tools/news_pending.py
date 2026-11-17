"""Local state history and once-only pending alerts."""
import json
from pathlib import Path
from datetime import timedelta
from tools.lib import iso_utc, parse_time

STATES = {'found', 'judged', 'published', 'held', 'rejected', 'answered'}


def read(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def write(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(p)


def record(path, cid, state, now, note=''):
    if state not in STATES:
        raise ValueError('invalid ledger state')
    data = read(path)
    row = data.setdefault(cid, {'first_seen': iso_utc(now), 'history': [], 'alerted': False})
    if row.get('state') != state or row.get('note') != note:
        row['history'].append({'state': state, 'time': iso_utc(now), 'note': note})
    row.update(state=state, note=note, updated=iso_utc(now))
    write(path, data)


def pending_over(path, now, minutes=10):
    return [cid for cid, r in read(path).items() if r['state'] in ('found', 'judged', 'held')
            and not r.get('alerted') and now - parse_time(r['first_seen']) >= timedelta(minutes=minutes)]


def alert_lines(path, now):
    ids = pending_over(path, now)
    data = read(path)
    lines = []
    for cid in ids:
        r = data[cid]
        lines.append('%s pending: %s (%s): %s' % (now.strftime('%H:%M UTC'), cid, r['state'], r.get('note', '')))
        r['alerted'] = True
    write(path, data)
    return lines


def hourly_line(path, now):
    data = read(path)
    counts = {s: set() for s in ('found', 'published', 'held', 'rejected')}
    held = {}
    for cid, row in data.items():
        for event in row['history']:
            if now - timedelta(minutes=60) <= parse_time(event['time']) <= now and event['state'] in counts:
                counts[event['state']].add(cid)
                if event['state'] == 'held':
                    held[cid] = event['note']
    return '%s hourly: found %d, published %d, held %d, rejected %d. Held: %s' % (
        now.strftime('%H:%M UTC'), *(len(counts[s]) for s in ('found', 'published', 'held', 'rejected')),
        '; '.join('%s: %s' % pair for pair in sorted(held.items())) or 'none')
