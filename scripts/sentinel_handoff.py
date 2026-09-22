#!/usr/bin/env python3
"""sentinel_handoff.py — bridge a bare wave_dispatch_sentinel (finite
runway, launched directly via dfork) to wave_sentinel_keepalive (unlimited
patience). 2026-09-22 overnight-outage coverage.

Why: the live prod031/hfx302 sentinels were launched bare (--rounds 100,
~7h runway). If the generation outage outlasts them during a session gap,
nothing restocks the queue. This watcher polls the bare sentinel's pid;
when it exits (rounds exhausted = exit 3, or crash), the handoff resolves
the lane's latest pin tab from the session registry, exports PATIENT_TAB,
and runs wave_sentinel_keepalive for the same job — which relaunches the
sentinel with a fresh round budget forever (exit 0 only when the lane is
generating; the sentinel's adoption path then self-terminates it).

Usage: sentinel_handoff.py <bare-pid> <name>:<prompt.md> [--every N]
       [--watch N] [--rounds N]
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
KEEPALIVE = os.path.join(BASE, "wave_sentinel_keepalive.py")


def log(line):
    print(time.strftime("[%H:%M:%S]") + f" [handoff] {line}", flush=True)


def latest_pin(name):
    """Newest registry tab_id for the lane (pins rotate; stale is fine —
    patient_dispatch falls back to any chat.z.ai tab, and the sentinel's
    hygiene mints fresh pins anyway)."""
    try:
        for line in reversed(open(REGISTRY).read().splitlines()):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("name") == name and rec.get("tab_id"):
                return str(rec["tab_id"])[:8]
    except FileNotFoundError:
        pass
    return ""


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pid = int(sys.argv[1])
    job = sys.argv[2]
    rest = sys.argv[3:]
    name = job.split(":", 1)[0]

    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(60)
    log(f"bare sentinel {pid} exited — handing lane {name} to keepalive")

    pin = latest_pin(name)
    if pin:
        os.environ["PATIENT_TAB"] = pin
        log(f"PATIENT_TAB={pin} (latest registry pin for {name})")

    while True:
        log(f"launching keepalive: {job} {' '.join(rest)}")
        rc = subprocess.call([sys.executable, KEEPALIVE, job] + rest, cwd=BASE)
        if rc == 0:
            log("keepalive exit 0 — lane generating; handoff complete")
            return 0
        log(f"keepalive exit {rc} — retry in 120s")
        time.sleep(120)


if __name__ == "__main__":
    raise SystemExit(main())
