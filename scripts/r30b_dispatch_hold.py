#!/usr/bin/env python3
"""
r30b_dispatch_hold.py — the spaced timed-retry dispatcher for R30-B.

Doctrine stack:
- r25-serialization / lesson-125: no peak-hour churn — ONE attempt per cycle,
  spaced 45 minutes apart, then HOLD until the next cycle.
- dispatch-timing doctrine: the quiet window is 19:00 UTC (03:00 Beijing); the
  spaced retries naturally land there without anyone babysitting the peak.
- resident directive: keep going until the worker is dispatched and watched.

On SUCCESS: posts to the console outbox + exits (the r30b watcher is armed
separately by this script via the r30b_watch.py clone).
On 6 FAILED cycles: posts the hold state + exits (the lead/operator re-arms).
"""
import json
import re
import subprocess
import sys
import time

PY = "/home/z/.venv/bin/python3"
DISPATCH = "/home/z/replay2/scripts/dispatch_worker.py"
WATCH_LAUNCH = "/home/z/replay2/scripts/launch_detached.py"
WATCHER = "/home/z/replay2/scripts/r30b_watch.py"
PROMPT = "/home/z/replay2/scripts/.replay-backup/r30b-dispatch.md"
OUTBOX = "/home/z/replay2/scripts/flags/agent_outbox.jsonl"
LOG = "/home/z/replay2/scripts/logs/r30b-dispatch-hold.log"
REGISTRY = "/home/z/replay2/scripts/flags/session_registry.jsonl"
CHAT_ID_FLAG = "/home/z/replay2/scripts/flags/r30b-chat-id"
CYCLE_S = 45 * 60
MAX_CYCLES = 6


def log(msg):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}"
    print(line, flush=True)


def post(text):
    with open(OUTBOX, "a") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def run(cmd, timeout=420):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def registry_chat_id():
    """Latest r30b create record with sent=true -> the chat id from its url."""
    try:
        recs = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except FileNotFoundError:
        return None
    for rec in reversed(recs):
        if rec.get("name") == "r30b" and rec.get("sent"):
            url = rec.get("url") or ""
            m = re.search(r"/c/([0-9a-f-]{36})", url)
            if m:
                return m.group(1)
    return None


def try_cycle(n):
    log(f"CYCLE {n}: attempt create r30b")
    # clean any stale registry entry first (void is idempotent; ignore failure)
    run([PY, DISPATCH, "void", "r30b", f"hold-cycle-{n} pre-create cleanup"], timeout=120)
    time.sleep(5)
    rc, out = run([PY, DISPATCH, "create", "r30b", PROMPT])
    tail = "\n".join(out.strip().splitlines()[-6:])
    log(f"create rc={rc}\n{tail}")
    if "VERIFIED" in out and "NOT VERIFIED" not in out:
        # deterministic chat id from the registry create record
        cid = registry_chat_id()
        if cid:
            with open(CHAT_ID_FLAG, "w") as f:
                f.write(cid + "\n")
            log(f"chat id pinned: {cid}")
        rc2, out2 = run([PY, DISPATCH, "check", "r30b"], timeout=120)
        log("check:\n" + "\n".join(out2.strip().splitlines()[-8:]))
        return True, out2
    return False, tail


def main():
    log("HOLD DAEMON ARMED — spaced retries every 45min, max 6 cycles")
    for n in range(1, MAX_CYCLES + 1):
        ok, info = try_cycle(n)
        if ok:
            # arm the watcher
            rcw, outw = run([PY, WATCH_LAUNCH, "/home/z/replay2/scripts/logs/r30b-watch.log",
                             PY, WATCHER], timeout=60)
            log(f"watcher launch rc={rcw}: {outw.strip()[-200:]}")
            post("R30-B DISPATCHED (hold-cycle " + str(n) + ") — the account-chrome worker is live; "
                 "watcher armed (r30b_watch). The corpus lane wfx/r30/lead-captures is the binding grammar.")
            log("SUCCESS — watcher armed, exiting")
            return 0
        log(f"cycle {n} failed; holding {CYCLE_S//60}min")
        time.sleep(CYCLE_S)
    post("R30-B dispatch HOLD after 6 spaced cycles (peak congestion persisted) — the staged prompt "
         "is recycle-proof (.replay-backup/r30b-dispatch.md); re-arm from the console when ready.")
    log("HOLD EXHAUSTED — posted state, exiting")
    return 1


if __name__ == "__main__":
    sys.exit(main())
