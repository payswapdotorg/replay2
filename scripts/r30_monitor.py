#!/usr/bin/env python3
"""r30_monitor.py — one-shot compact status for the R30-B pipeline (lead loop).

Prints: time | peak/quiet hold states | dispatch flags | worker chat state |
        stack heartbeats. Exit 10 if R30-B DISPATCHED (chat-id pinned),
        exit 20 if worker COMPLETE, exit 30 if DEAD, else 0.
"""
import json
import os
import subprocess
import sys
import time

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
FLAGS = f"{BASE}/flags"
CHATS = f"{BASE}/chats_http.py"


def tail(path, n=3):
    try:
        lines = open(path).read().strip().splitlines()
        return lines[-n:]
    except FileNotFoundError:
        return ["(no log)"]


def main():
    now = time.strftime("%H:%M:%S", time.gmtime())
    print(f"=== {now}Z ===")

    # hold daemons
    for name, log in (("peak", f"{BASE}/logs/r30b-dispatch-hold.log"),
                      ("quiet", f"{BASE}/logs/r30b-quiet-hold.log")):
        for l in tail(log, 2):
            print(f"[{name}] {l}")

    # dispatch + completion flags
    for flag, label in (("r30b-chat-id", "CHAT-ID"),
                        ("r30b-complete", "COMPLETE"),
                        ("r30b-dead", "DEAD")):
        p = f"{FLAGS}/{flag}"
        if os.path.isfile(p):
            val = open(p).read().strip()[:60]
            print(f"[FLAG] {label}: {val}")

    # watcher log (arms on dispatch)
    for l in tail(f"{BASE}/logs/r30b-watch.log", 3):
        print(f"[watch] {l}")

    # worker chat detail (if pinned)
    cid_path = f"{FLAGS}/r30b-chat-id"
    if os.path.isfile(cid_path):
        cid = open(cid_path).read().strip()
        p = subprocess.run([PY, CHATS, "detail", cid],
                           capture_output=True, text=True, timeout=60)
        out = (p.stdout or "") + (p.stderr or "")
        for l in out.strip().splitlines()[:12]:
            print(f"[chat] {l}")

    # heartbeats freshness (age in seconds)
    now_t = time.time()
    for hb in ("supervisor_heartbeat", "custodian_heartbeat",
               "watcher_heartbeat", "stall_recovery_heartbeat"):
        p = f"{FLAGS}/{hb}"
        try:
            age = int(now_t - os.path.getmtime(p))
            print(f"[hb] {hb}: {age}s")
        except OSError:
            print(f"[hb] {hb}: MISSING")

    # exit codes for the lead loop
    if os.path.isfile(f"{FLAGS}/r30b-complete"):
        return 20
    if os.path.isfile(f"{FLAGS}/r30b-dead"):
        return 30
    if os.path.isfile(cid_path):
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
