#!/usr/bin/env python3
"""spaced_send.py — patient single-shot send loop for gate-blocked sessions.

The 13-round assault burns allowance into the same cooldown (lesson 61
treadmill, re-proven 2026-09-12 peak gate: 26 consecutive rejected Enters).
This loop sends ONE round per interval and trusts the server-side verify
(dispatch_worker.send prints VERIFIED only on a real commit).

Usage: spaced_send.py <session-name> <@prompt-file> [interval-s, default 240]

Stops on VERIFIED (exit 0) or after max attempts (exit 4). Run detached via
launch_detached.py; watch the log.
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

name, prompt = sys.argv[1], sys.argv[2]
interval = int(sys.argv[3]) if len(sys.argv) > 3 else 240
MAX = int(os.environ.get("SPACED_MAX", "40"))

send_log = os.path.join(BASE, "logs", f"send_{name}.log")

for attempt in range(1, MAX + 1):
    stamp = time.strftime("%H:%M:%S")
    print(f"[{name}] {stamp} spaced attempt {attempt}/{MAX} (1 round, DW_ROUNDS=1)", flush=True)
    env = dict(os.environ, DW_ROUNDS="1")
    p = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
         "send", name, prompt],
        cwd=BASE, env=env, capture_output=True, text=True, timeout=180)
    tail = (p.stdout or "").strip().split("\n")
    verdict = tail[-1] if tail else "?"
    print(f"[{name}] {stamp} verdict: {verdict[:160]}", flush=True)
    if "VERIFIED" in verdict and "NOT VERIFIED" not in verdict:
        print(f"[{name}] {stamp} LANDED SERVER-SIDE — done", flush=True)
        sys.exit(0)
    if p.returncode == 3:
        print(f"[{name}] {stamp} rate-limit bail — backing off one interval", flush=True)
    time.sleep(interval)

print(f"[{name}] exhausted {MAX} spaced attempts", flush=True)
sys.exit(4)
