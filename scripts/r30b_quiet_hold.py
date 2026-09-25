#!/usr/bin/env python3
"""
r30b_quiet_hold.py — the successor hold for R30-B (quiet-window convergence).

Doctrine stack:
- r25-serialization / lesson-125: no peak-hour churn — ONE attempt per cycle,
  spaced ONE HOUR apart (more conservative than the peak daemon's 45min),
  converging on the 19:00 UTC (03:00 Beijing) quiet window.
- diagnosis (r30-cycle-7, 11:5xZ): the model-menu popover opens but renders
  ZERO options during the evening peak (the option-list fetch hangs) — the
  "GLM-5.3 option not found" failures are congestion, not removal. Cycling
  is correct; the menu will render when the platform recovers.
- resident directive: keep going until the worker is dispatched and watched.

Succession law: waits for the predecessor (r30b_dispatch_hold.py, pid in
arg 1 or flags/r30b-peak-hold.pid) to EXIT, then checks flags/r30b-chat-id:
  - exists -> the predecessor SUCCEEDED; exit 0 (watcher already armed).
  - absent  -> the predecessor exhausted; start the hourly cycles.

On SUCCESS: pins chat id, arms the r30b watcher, posts to the outbox, exits.
On MAX_CYCLES exhausted: posts the hold state, exits (the lead re-arms).
"""
import json
import os
import re
import subprocess
import sys
import time

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
DISPATCH = f"{BASE}/dispatch_worker.py"
WATCH_LAUNCH = f"{BASE}/launch_detached.py"
WATCHER = f"{BASE}/r30b_watch.py"
PROMPT = f"{BASE}/.replay-backup/r30b-dispatch.md"
OUTBOX = f"{BASE}/flags/agent_outbox.jsonl"
LOG = f"{BASE}/logs/r30b-quiet-hold.log"
REGISTRY = f"{BASE}/flags/session_registry.jsonl"
CHAT_ID_FLAG = f"{BASE}/flags/r30b-chat-id"
CYCLE_S = 60 * 60          # hourly — more conservative than the peak daemon
MAX_CYCLES = 8             # ~14:30 -> 21:30Z, spanning the 19:00Z quiet window
PREDECESSOR_WAIT_S = 4 * 3600


def log(msg):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}"
    print(line, flush=True)


def post(text):
    with open(OUTBOX, "a") as f:
        f.write(json.dumps(
            {"ts": int(time.time() * 1000), "from": "agent", "text": text}
        ) + "\n")


def run(cmd, timeout=420):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


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
    run([PY, DISPATCH, "void", "r30b", f"quiet-cycle-{n} pre-create cleanup"],
        timeout=120)
    time.sleep(5)
    rc, out = run([PY, DISPATCH, "create", "r30b", PROMPT])
    tail = "\n".join(out.strip().splitlines()[-6:])
    log(f"create rc={rc}\n{tail}")
    if "VERIFIED" in out and "NOT VERIFIED" not in out:
        cid = registry_chat_id()
        if cid:
            with open(CHAT_ID_FLAG, "w") as f:
                f.write(cid + "\n")
            log(f"chat id pinned: {cid}")
        rc2, out2 = run([PY, DISPATCH, "check", "r30b"], timeout=120)
        log("check:\n" + "\n".join(out2.strip().splitlines()[-8:]))
        return True, out2
    return False, tail


def arm_watcher():
    rcw, outw = run([PY, WATCH_LAUNCH,
                     f"{BASE}/logs/r30b-watch.log", PY, WATCHER], timeout=60)
    log(f"watcher launch rc={rcw}: {outw.strip()[-200:]}")


def main():
    # --- succession: wait for the predecessor, then check its outcome ---
    pred_pid = None
    if len(sys.argv) > 1:
        try:
            pred_pid = int(sys.argv[1])
        except ValueError:
            pass
    if pred_pid:
        log(f"SUCCESSOR ARMED — waiting for predecessor pid {pred_pid} to exit")
        t0 = time.time()
        while pid_alive(pred_pid) and time.time() - t0 < PREDECESSOR_WAIT_S:
            time.sleep(60)
        if pid_alive(pred_pid):
            log("predecessor still alive after 4h — exiting to avoid a race "
                "(the lead will re-arm)")
            return 3
        log("predecessor exited")
    if os.path.isfile(CHAT_ID_FLAG):
        log("r30b-chat-id flag present — the predecessor SUCCEEDED; "
            "nothing to do")
        return 0
    log("predecessor exhausted without a landing — the quiet-window cycles "
        f"begin (hourly x{MAX_CYCLES}, converging on the 19:00Z window)")
    for n in range(1, MAX_CYCLES + 1):
        ok, _info = try_cycle(n)
        if ok:
            arm_watcher()
            post("R30-B DISPATCHED (quiet-hold cycle " + str(n) + ") — the "
                 "account-chrome worker is live; watcher armed (r30b_watch). "
                 "The corpus lane wfx/r30/lead-captures is the binding grammar.")
            log("SUCCESS — watcher armed, exiting")
            return 0
        log(f"cycle {n} failed; holding {CYCLE_S//60}min")
        time.sleep(CYCLE_S)
    post("R30-B dispatch HOLD exhausted after the quiet-window cycles — the "
         "staged prompt remains recycle-proof (.replay-backup/r30b-dispatch.md); "
         "the lead re-arms from the console.")
    log("HOLD EXHAUSTED — posted state, exiting")
    return 1


if __name__ == "__main__":
    sys.exit(main())
