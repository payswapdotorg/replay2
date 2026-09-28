#!/usr/bin/env python3
"""wave3_revival_watchdog.py — keep wave3_revival.py alive + cycling.

The daemon occasionally wedges in a single kernel-level ETIMEDOUT (~15 min)
despite per-call timeouts; cycles stall; cures lag. This watchdog:
  - every 300s: check the daemon log's mtime (a healthy daemon logs a
    cycle at least every ~15 min even at worst-case slow cycles)
  - stale > 720s with the process alive -> kill it (state persists on disk)
  - process dead -> relaunch via dfork_launch.py (double-fork, reaper-proof)
Idempotent; safe to run alongside the frame_guard/supervisor ring.
"""
import os
import subprocess
import time

BASE = "/home/z/replay2/scripts"
LOG = os.path.join(BASE, "logs", "wave3_revival.log")
PY = "/home/z/.venv/bin/python3"
STALE = 720
CHECK = 300


def pid_of():
    try:
        r = subprocess.run(["pgrep", "-f", "wave3_revival.py"],
                           capture_output=True, text=True, timeout=10)
        pids = [p for p in r.stdout.split() if p.strip()]
        return pids[0] if pids else None
    except Exception:
        return None


def stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


while True:
    try:
        mtime = os.path.getmtime(LOG) if os.path.exists(LOG) else 0
        stale = time.time() - mtime
        p = pid_of()
        if stale > STALE and p:
            with open(LOG, "a") as f:
                f.write(f"{stamp()} [watchdog] log stale {int(stale)}s — "
                        f"killing wedged pid {p}\n")
            try:
                os.kill(int(p), 15)
            except ProcessLookupError:
                pass
            time.sleep(3)
            p = None
        if not p:
            with open(LOG, "a") as f:
                f.write(f"{stamp()} [watchdog] relaunching daemon\n")
            subprocess.run(
                [PY, os.path.join(BASE, "dfork_launch.py"), LOG,
                 PY, "wave3_revival.py"],
                cwd=BASE, timeout=30, capture_output=True)
    except Exception as e:
        with open(LOG, "a") as f:
            f.write(f"{stamp()} [watchdog] error: {e}\n")
    time.sleep(CHECK)
