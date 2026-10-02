#!/usr/bin/env python3
"""wave3_remote_watch.py — detached remote watch for the payswap.org roadmap frontier.

Roadmap-complete mode (9205e35, hardened 2026-10-02 evening):
Polls the remote (ls-remote + the phase-2-state.json blob) every POLL_S:
  - main moving (any new operator-recorded work landing on main)
  - ROADMAP COMPLETE notice: the phase_complete closure block (the
    do_not_redispatch marker) OR all-frontier-COMPLETE with nothing active.
    NOTE completed_work_orders alone is NOT exhaustive — the closure record
    lives in frontier status COMPLETE + the phase_complete block (the first
    run of this script caught that: P2-W2-003/P2-W3-003 never appeared in
    completed_work_orders, so the old detection could never fire).
  - ROADMAP REOPENED: the closure marker disappearing or active work
    appearing after completion (new operator-recorded phase/work).
  - active work orders appearing / READY frontier entries appearing.
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
            "frontier": [(f.get("id"), f.get("status")) for f in d.get("frontier", [])],
            "frontier_ready": [f.get("id") for f in d.get("frontier", []) if f.get("status") == "READY"],
            "phase": d.get("phase"),
            "phase_complete": bool(d.get("phase_complete", {}).get("do_not_redispatch")),
        }
    except Exception:
        pass
    return {"main": main[:12], "w1_003": (w1 or "")[:12], "state": parsed}


def roadmap_complete(st):
    """The closure record: the phase_complete block's do_not_redispatch marker,
    or (fallback) every frontier item COMPLETE with nothing active."""
    if not st:
        return False
    if st.get("phase_complete"):
        return True
    frontier = st.get("frontier") or []
    return bool(frontier) and all(s == "COMPLETE" for _, s in frontier) and not st.get("active")


def main():
    prev = None
    alerted_complete = False
    log("wave3 remote watch started (roadmap-complete mode, hardened)")
    while True:
        snap = snapshot()
        st = snap["state"]
        if prev is None:
            log("baseline main=%s w1_003=%s active=%s phase=%s" % (
                snap["main"], snap["w1_003"] or "-", st.get("active"), st.get("phase")))
        else:
            if snap["main"] != prev["main"]:
                log("MAIN MOVED %s -> %s (active=%s completed=%s)" % (prev["main"], snap["main"], st.get("active"), st.get("completed")))
                outbox("wave3 watch: payswap.org main moved %s -> %s; active=%s completed=%s" % (prev["main"], snap["main"], st.get("active"), st.get("completed")))
            if snap["w1_003"] != prev["w1_003"] and snap["w1_003"]:
                log("P2-W1-003 BRANCH at %s" % snap["w1_003"])
            # NEW operator-recorded work: active work orders appearing
            prev_active = set(prev["state"].get("active") or [])
            new_active = [a for a in (st.get("active") or []) if a not in prev_active]
            if new_active:
                log("ACTIVE WORK APPEARED %s" % new_active)
                outbox("wave3 watch: NEW ACTIVE WORK on payswap.org: %s (main=%s) — operator-recorded dispatch" % (new_active, snap["main"]))
            # NEW operator-recorded work: READY frontier entries appearing
            prev_ready = set(prev["state"].get("frontier_ready") or [])
            new_ready = [r for r in (st.get("frontier_ready") or []) if r not in prev_ready]
            if new_ready:
                log("FRONTIER READY APPEARED %s" % new_ready)
                outbox("wave3 watch: FRONTIER READY on payswap.org: %s (main=%s)" % (new_ready, snap["main"]))
        # roadmap-complete detection: the phase_complete closure block, or
        # all-frontier-COMPLETE with nothing active (completed_work_orders is
        # NOT exhaustive — P2-W2-003/P2-W3-003 close via frontier + block)
        complete = roadmap_complete(st)
        if not alerted_complete and complete:
            log("ROADMAP COMPLETE detected (phase=%s frontier=%s)" % (st.get("phase"), st.get("frontier")))
            outbox("ROADMAP COMPLETE: payswap.org Phase 2 all orders done (watcher-confirmed at main %s). Monitoring continues for NEW operator-recorded work (commits/branches/state changes)." % snap["main"])
            alerted_complete = True
        elif alerted_complete and st and st.get("phase") and not complete:
            # the closure marker vanished or active work appeared: reopened.
            # (st["phase"] present guards against a degenerate/truncated state
            # blob parsing as an empty-ish dict — that is transient, not a reopen)
            log("ROADMAP REOPENED (active=%s frontier=%s)" % (st.get("active"), st.get("frontier")))
            outbox("wave3 watch: payswap.org ROADMAP REOPENED at main %s — active=%s frontier=%s" % (snap["main"], st.get("active"), st.get("frontier")))
            alerted_complete = False
        try:
            json.dump({"ts": int(time.time()), "snap": snap, "alerted_complete": alerted_complete}, open(STATE_F, "w"))
        except Exception:
            pass
        prev = snap
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
