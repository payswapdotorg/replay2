#!/usr/bin/env python3
"""wave_sentinel_keepalive.py — patience wrapper for wave_dispatch_sentinel.

2026-09-21 13:1x: the platform's GLM-5.3 fleet is at peak-hours capacity
(plain/default-model chats materialize + reply; every GLM-5.3 send —
plain or agent-mode — creates a client shell the server never accepts).
House law fixes workers at GLM-5.3 + Full-Stack, so the only lawful path
is to keep rotating fresh dispatches until the gate opens.

wave_dispatch_sentinel exits 0 when every name is generating and 3 when a
name exhausts its bounded rounds (~5h at current cadence) — a deliberate
churn bound. This wrapper preserves that bound per invocation while giving
the wave unlimited overall patience: on exit 3 it sleeps RESTART_SLEEP and
relaunches the sentinel (fresh round budget). On exit 0 it stops. Any other
exit (crash) gets CRASH_SLEEP and one restart attempt per cycle too — the
operator can kill this wrapper (pid in flags/wave_keepalive.pid) to stop.

Usage (identical job args to wave_dispatch_sentinel):
  wave_sentinel_keepalive.py <name>:<prompt.md> [...] [--every N] \
      [--watch N] [--rounds N]
Env: PATIENT_TAB (passed through to patient_dispatch)
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SENTINEL = os.path.join(BASE, "wave_dispatch_sentinel.py")
PIDFILE = os.path.join(BASE, "flags", "wave_keepalive.pid")
# per-lane pidfile (2026-09-23): multiple lanes can run keepalives
# concurrently and clobber the legacy shared PIDFILE (last writer wins);
# supervisor's ensure_lane_keepalive() tracks each lane by THIS file.
NAME = (sys.argv[1].split(":", 1)[0]
        if len(sys.argv) > 1 and ":" in sys.argv[1] else "wave")
LANE_PIDFILE = os.path.join(BASE, "flags", f"wave_keepalive.pid.{NAME}")
RESTART_SLEEP = 120   # seconds between sentinel invocations
CRASH_SLEEP = 300     # extra patience if the sentinel itself crashed

open(PIDFILE, "w").write(str(os.getpid()))
open(LANE_PIDFILE, "w").write(str(os.getpid()))


def log(line):
    print(time.strftime("[%H:%M:%S]") + f" [keepalive] {line}", flush=True)


def main():
    jobs = sys.argv[1:]
    if not jobs:
        print(__doc__)
        return 2
    while True:
        log(f"launching sentinel: {' '.join(jobs)}")
        rc = subprocess.call([sys.executable, SENTINEL] + jobs, cwd=BASE)
        if rc == 0:
            log("sentinel exit 0 — every name generating; done")
            return 0
        log(f"sentinel exit {rc} — sleeping {RESTART_SLEEP}s, then fresh rounds")
        time.sleep(RESTART_SLEEP if rc == 3 else CRASH_SLEEP)


if __name__ == "__main__":
    raise SystemExit(main())
