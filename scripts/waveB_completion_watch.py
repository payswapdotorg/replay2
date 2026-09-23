#!/usr/bin/env python3
"""waveB_completion_watch.py — passive completion observer for Wave B.

Polls each live session's batch store via batch_probe (CDP-free server
truth) and applies the filled-report gate (40-hex sha in the 450-char
marker window, no placeholders — immune to packet-template echoes). On a
genuine completion:

  1. writes flags/<name>-complete.marker;
  2. posts the operator outbox ping.

NO dispatch power, NO assault behavior, NO tab manipulation — purely
passive reading. The Lead handles harvest/merge in its own passes.

Usage: waveB_completion_watch.py <name>:<chat-id> [<name>:<chat-id> ...]
       [--every 150] [--max-hours 14]
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")

MARKERS = {
    "prod022": "PROD-022 COMPLETION REPORT",
    "prod023": "PROD-023 COMPLETION REPORT",
    "prod018": "PROD-018 COMPLETION REPORT",
    # 2026-09-22 lesson (prod030): a worker may TRANSLATE the packet's report
    # template (prod030 posted "PROD-030 完成报告"). The watch value is now a
    # list — ANY member fires (the filled-report gate itself still protects
    # against packet-template echoes: hex40 in window + no placeholder).
    "prod030": ["PROD-030 COMPLETION REPORT", "PROD-030 完成报告"],
    "prod031": ["PROD-031 COMPLETION REPORT", "PROD-031 完成报告", "WORKER_COMMIT"],
    "hfx204": ["HFX-204 COMPLETION REPORT", "HFX-204 完成报告", "WORKER_COMMIT"],
    "hfx301": ["HFX-301 COMPLETION REPORT", "HFX-301 完成报告", "WORKER_COMMIT"],
    # 2026-09-23 endgame lanes (names lack the hyphen; the packets' headlines have it)
    "prod033": ["PROD-033 COMPLETION REPORT", "PROD-033 完成报告", "WORKER_COMMIT"],
    "hfx302": ["HFX-302 COMPLETION REPORT", "HFX-302 完成报告", "WORKER_COMMIT"],
}


def log(line):
    print(time.strftime("[%H:%M:%S]") + f" [done-watch] {line}", flush=True)


def post_outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception as e:
        log(f"outbox write failed: {e}")


def probe(name, cid):
    """Run batch_probe for each marker variant; returns (ok, report, err)."""
    markers = MARKERS.get(name, [f"{name.upper()} COMPLETION REPORT", f"{name.upper()} 完成报告"])
    if isinstance(markers, str):
        markers = [markers]
    last_err = None
    for marker in markers:
        try:
            out = subprocess.run(
                [sys.executable, os.path.join(BASE, "batch_probe.py"), cid, marker],
                capture_output=True, text=True, timeout=120)
            txt = out.stdout.strip() or out.stderr.strip()
            if '"err"' in txt:
                last_err = txt[:80]
                continue
            d = json.loads(txt)
            return True, bool(d.get("report")), None
        except Exception as e:
            last_err = str(e)[:80]
    return False, False, last_err


def main():
    jobs = []
    args = sys.argv[1:]
    every, max_s = 150, 14 * 3600
    for a in args:
        if a.startswith("--every"):
            every = int(a.split("=", 1)[1])
        elif a.startswith("--max-hours"):
            max_s = int(a.split("=", 1)[1]) * 3600
        elif ":" in a:
            n, c = a.split(":", 1)
            jobs.append((n, c))
    if not jobs:
        print(__doc__)
        return 2
    done = set()
    for n, _ in jobs:
        if os.path.exists(os.path.join(FLAGS, f"{n}-complete.marker")):
            done.add(n)
    log(f"watching {[(n, c[:8]) for n, c in jobs]}; already complete: {sorted(done) or 'none'}")
    t0 = time.time()
    err_streak = 0
    while len(done) < len(jobs) and time.time() - t0 < max_s:
        time.sleep(every)
        for n, c in jobs:
            if n in done:
                continue
            ok, report, err = probe(n, c)
            if err:
                err_streak += 1
                if err_streak % 20 == 1:  # note persistent API trouble, don't spam
                    log(f"{n} {c[:8]}: API trouble ({err}) — streak {err_streak}")
                continue
            err_streak = 0
            if ok and report:
                done.add(n)
                open(os.path.join(FLAGS, f"{n}-complete.marker"), "w").write(
                    f"{n} complete chat={c} at {time.strftime('%H:%M:%S')}\n")
                log(f"{n} COMPLETE (filled-report gate TRUE) chat {c[:8]}")
                post_outbox(f"{n.upper()} COMPLETE — the worker posted its filled "
                            f"completion report (server-verified, marker+sha gate). "
                            f"The Lead will now harvest the delivery, re-run the gates "
                            f"and merge. Wave B remaining: {sorted(set(j[0] for j in jobs) - done) or 'none — wave done'}.")
    log(f"done; complete={sorted(done)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
