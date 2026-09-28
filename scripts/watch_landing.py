#!/usr/bin/env python3
"""watch_landing.py — resident landing-watch for the qa004/qa005 freeze fight.

Polls every 60s (default 9 rounds) for the three landing signals:
  (a) a NEW workspace row (allocations resumed — any chat other than the
      known QA003 zombie chat-138dc4f2)
  (b) a fighter flag CLEARED (capacity_recover.qa00X.json gone = the lane
      landed server-verified)
  (c) a fighter process DEAD (machinery failure — needs TL attention)
Exits early with the signal line when any fires; prints steady-state
otherwise. Read-only: never touches the fighters, the registry, or tabs.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
TOKEN_PATH = os.path.join(FLAGS, "chat_token")
ZOMBIE_PREFIX = "chat-138dc4f2"  # QA003 zombie workspace (pod long gone)
LANES = ("qa004", "qa005")


def workspaces():
    tok = open(TOKEN_PATH).read().strip()
    req = urllib.request.Request(
        "https://chat.z.ai/api/v1/web-dev/workspaces/user-fc",
        headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def fighters_alive():
    out = subprocess.run(["pgrep", "-af", "recover_capacity"],
                         capture_output=True, text=True).stdout.strip()
    return len([l for l in out.split("\n") if l.strip()])


def check():
    """Return a signal string, or None for steady state."""
    # (b) flags cleared
    for lane in LANES:
        p = os.path.join(FLAGS, f"capacity_recover.{lane}.json")
        if not os.path.exists(p):
            return f"SIGNAL: flag {lane} CLEARED — lane landed (server-verified)"
    # (a) new workspace row
    try:
        d = workspaces()
        new = [w for w in d.get("workspaces", [])
               if not w["chat_id"].startswith(ZOMBIE_PREFIX)]
        if new:
            for w in new:
                return (f"SIGNAL: NEW workspace {w['chat_id'][:18]} "
                        f"title={w.get('chat_title','')!r} — allocations RESUMED")
    except Exception as e:
        return None  # probe failure is not a landing signal
    # (c) fighters dead
    n = fighters_alive()
    if n < 2:
        return f"SIGNAL: only {n} fighter(s) alive — machinery needs attention"
    return None


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    for i in range(rounds):
        sig = check()
        if sig:
            print(f"[{time.strftime('%H:%M:%SZ', time.gmtime())}] {sig}", flush=True)
            return 0
        time.sleep(60)
    print(f"[{time.strftime('%H:%M:%SZ', time.gmtime())}] steady: freeze holds, "
          f"fighters alive, no new allocations", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
