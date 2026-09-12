#!/usr/bin/env python3
"""freeze_revive.py — wait out a usage-cap window, then revive a worker session.

Usage: freeze_revive.py <session> <@prompt-file> <resume-epoch-seconds> [interval-s, default 480]

Hard-sleeps (NO sends — never re-arm) until the resume epoch, then sends
ONE round per interval with server-side verification until the content
lands. Exits 0 on landing.
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))

if len(sys.argv) < 4:
    print(__doc__)
    sys.exit(2)

name, prompt = sys.argv[1], sys.argv[2]
resume_at = int(sys.argv[3])
interval = int(sys.argv[4]) if len(sys.argv) > 4 else 480

now = time.time()
wait_s = resume_at - now
if wait_s > 0:
    print(f"[{name}] freeze: sleeping {int(wait_s)}s until {time.strftime('%H:%M:%S', time.localtime(resume_at))} (no sends — never re-arm)", flush=True)
    time.sleep(wait_s)

print(f"[{name}] resume window: single-round sends every {interval}s until landed", flush=True)
env = dict(os.environ, DW_ROUNDS="1")
attempt = 0
while True:
    attempt += 1
    stamp = time.strftime("%H:%M:%S")
    print(f"[{name}] {stamp} revival attempt {attempt} (1 round)", flush=True)
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "send", name, prompt],
            cwd=BASE, env=env, capture_output=True, text=True, timeout=180)
        out = (p.stdout or "") + (p.stderr or "")
        lines = [l for l in out.split("\n") if l.strip()]
        verdict = lines[-1] if lines else "?"
        print(f"[{name}] {stamp} verdict: {verdict[:150]}", flush=True)
        if "VERIFIED" in verdict and "NOT VERIFIED" not in verdict:
            print(f"[{name}] {stamp} REVIVAL LANDED", flush=True)
            sys.exit(0)
        # a rate-limit bail = the cap is STILL armed — extend the freeze by
        # the full interval (never grind)
        if "rate-limited" in out:
            print(f"[{name}] {stamp} rate-limit bail — extending freeze one interval", flush=True)
    except subprocess.TimeoutExpired:
        print(f"[{name}] {stamp} send round timed out — next interval", flush=True)
    time.sleep(interval)
