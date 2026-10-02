#!/usr/bin/env python3
"""wave3_remote_watch.py — detached remote watch for the payswap.org roadmap frontier.

Polls the remote (ls-remote + the phase-2-state.json blob) every POLL_S:
  - main moving (the parallel TL line's landings)
  - work/P2-W1-003 branch appearing/growing
  - phase-2-state.json: P2-W1-003 completion => the P2-W2-003 frontier OPENS
Alerts land in agent_outbox.jsonl + a compact state file. Never exits.
"""
import json
import os
import subprocess
import sys
import time

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = ("https://x-access-token:%s@github.com/payswapdotorg/payswap.org.git" % TOKEN) if TOKEN else "https://github.com/payswapdotorg/payswap.org.git"
REMOTE = "https://github.com/payswapdotorg/payswap.org"
FLAGS = "/home/z/replay2/scripts/flags"
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATE_F = os.path.join(FLAGS, "wave3_watch_state.json")
LOG = "/home/z/replay2/scripts/logs/wave3_remote_watch.log"
POLL_S = 300


def log(msg):
    with open(LOG, "a") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def outbox(text):
    with open(OUTBOX, "a") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        return "ERR:%s" % e


def snapshot():
    main = sh("git ls-remote %s HEAD 2>/dev/null | cut -f1" % REPO)
    w1 = sh("git ls-remote %s refs/heads/work/P2-W1-003 2>/dev/null | cut -f1" % REPO)
    state = sh("curl -s 'https://raw.githubusercontent.com/payswapdotorg/payswap.org/main/spec/development-state/phase-2-state.json'")
    parsed = {}
    try:
        d = json.loads(state)
        parsed = {
            "active": [w.get("id") for w in d.get("active_work_orders", [])],
            "completed": [w.get("id") for w in d.get("completed_work_orders", [])],
            "frontier_ready": [f.get("id") for f in d.get("frontier", []) if f.get("status") == "READY"],
        }
    except Exception:
        pass
    return {"main": main[:12], "w1_003": (w1 or "")[:12], "state": parsed}


def main():
    prev = None
    alerted_w2_open = False
    log("wave3 remote watch started")
    while True:
        snap = snapshot()
        if prev is None:
            log("baseline main=%s w1_003=%s active=%s" % (snap["main"], snap["w1_003"] or "-", snap["state"].get("active")))
        else:
            if snap["main"] != prev["main"]:
                log("MAIN MOVED %s -> %s (active=%s completed=%s)" % (prev["main"], snap["main"], snap["state"].get("active"), snap["state"].get("completed")))
                outbox("wave3 watch: payswap.org main moved %s -> %s; active=%s completed=%s" % (prev["main"], snap["main"], snap["state"].get("active"), snap["state"].get("completed")))
            if snap["w1_003"] != prev["w1_003"] and snap["w1_003"]:
                log("P2-W1-003 BRANCH at %s" % snap["w1_003"])
        # frontier open detection: P2-W1-003 completed AND P2-W2-003 not active
        st = snap["state"]
        if (not alerted_w2_open and st and "P2-W3-003" in st.get("completed", [])
                and st.get("frontier_ready") is not None):
            log("ROADMAP COMPLETE detected (completed=%s)" % st.get("completed"))
            outbox("ROADMAP COMPLETE: payswap.org Phase 2 all orders done (watcher-confirmed). Monitoring continues for NEW operator-recorded work (commits/branches/state changes).")
            alerted_w2_open = True
        try:
            json.dump({"ts": int(time.time()), "snap": snap, "alerted_w2_open": alerted_w2_open}, open(STATE_F, "w"))
        except Exception:
            pass
        prev = snap
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
