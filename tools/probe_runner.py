"""Run the probes. Plain code, no model calls.

  python tools/probe_runner.py --once --state state.json --out data/probes.json      one cycle, then exit
  python tools/probe_runner.py --loop 3300 --state state.json --out data/probes.json  cycles every 180 s for 3300 s

Each cycle probes the 30 services of tools/probe_list.json, spaced 2 s apart, at most once per 180 s per service.
Every GET is logged to the --log file (one JSON line each), so the spacing can be checked.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import probes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", default=None)
    ap.add_argument("--list", default=os.path.join(HERE, "probe_list.json"))
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds to keep cycling")
    ap.add_argument("--spacing", type=float, default=2.0, help="seconds between two probes in one cycle")
    a = ap.parse_args(argv)
    services = probes.load_json(a.list, [])
    state = probes.load_json(a.state, {})
    last = {}
    for sid, st in state.get("services", {}).items():
        if st.get("history"):
            last[sid] = probes.parse(st["history"][-1]["t"])
    end = time.time() + a.loop
    while True:
        now = datetime.now(timezone.utc)
        done = []
        for svc in services:
            lp = last.get(svc["id"])
            if lp and (now - lp).total_seconds() < probes.INTERVAL_S:
                continue
            res = probes.probe_once(svc, datetime.now(timezone.utc))
            last[svc["id"]] = probes.parse(res["t"])
            probes.update(state, svc, res)
            done.append((svc["id"], res))
            if a.log:
                with open(a.log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": svc["id"], "t": res["t"], "code": res["code"], "ms": res["ms"], "err": res["err"]}) + "\n")
            time.sleep(a.spacing)
        now = datetime.now(timezone.utc)
        probes.prune(state, now)
        save(a.state, state)
        snap = probes.snapshot(state, services, now)
        save(a.out, snap)
        bad = [s for s in snap["services"] if s["status"] in ("down", "degraded")]
        print("%s probed=%d bad=%d unprobeable=%d" % (probes.iso(now), len(done), len(bad), sum(1 for s in snap["services"] if s["status"] == "unprobeable")), flush=True)
        if a.once or time.time() >= end:
            return 0
        time.sleep(max(1, probes.INTERVAL_S - (time.time() - now.timestamp())))


if __name__ == "__main__":
    sys.exit(main())
