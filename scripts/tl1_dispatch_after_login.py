#!/usr/bin/env python3
"""tl1_dispatch_after_login.py — TL1 (Flauz substrate) program sentinel: fires
the first-sprint worker dispatches the instant the operator completes the
chat.z.ai login (fresh browser profile after sandbox reset #5, 2026-09-27).

On login:
  1. dispatch tl1-a-001 / tl1-b-002 / tl1-c-003 (sequential creates via
     dispatch_worker.py — full assault machinery incl. sandbox-limit release
     handling) — the 3-slot first sprint (tl1-a-004 queued next, cap = 3);
  2. arm one queue_watch watcher per session (launch_queue_watch), markers
     "TL1-00X COMPLETION REPORT" (the TL1 gate is in queue_watch.py);
  3. outbox notice at every transition; exit when the round is complete.

Re-entry guard: a session already live in the registry (action not in
void/failed/done) is never re-dispatched — its watcher is re-armed instead,
so a sentinel restart can never double-dispatch a live worker.

Usage: tl1_dispatch_after_login.py   (run detached via launch_detached.py)
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "tl1_dispatch.log")
POLL_SECS = 45
MAX_WAIT_SECS = 6 * 3600  # give up after 6h (operator may be away)
TERMINAL = ("void", "failed", "done")

SESSIONS = [
    ("tl1-a-001", "TL1-001 COMPLETION REPORT"),
    ("tl1-b-002", "TL1-002 COMPLETION REPORT"),
    ("tl1-c-003", "TL1-003 COMPLETION REPORT"),
]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def outbox(text):
    try:
        msg = {"ts": int(time.time() * 1000), "from": "agent", "text": text}
        with open(os.path.join(BASE, "flags", "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps(msg) + "\n")
    except OSError:
        pass


def login_state():
    """True when chat.z.ai no longer shows Sign in (operator logged in)."""
    try:
        for t in channel.list_tabs():
            url = t.get("url") or ""
            if url.startswith("https://chat.z.ai") and "/c/" not in url:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                body = dw._eval(c, "document.body.innerText || ''", timeout=20) or ""
                c.close()
                if body and "Sign in" not in body and "Log in" not in body:
                    return True
                return False
        # no chat.z.ai home tab at all — open one
        channel.new_tab("https://chat.z.ai/")
        time.sleep(4)
        return False
    except Exception as e:
        log(f"login probe error {type(e).__name__} — retrying")
        return False


def arm_watcher(name, marker):
    rec = dw._find(name)
    tab = (rec.get("tab_id") or "")[:8] if rec else ""
    if not tab:
        log(f"{name}: no registry tab — watcher NOT armed")
        return False
    w = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_queue_watch.py"), name, tab, marker],
        cwd=BASE, timeout=60, capture_output=True, text=True)
    log(f"{name} watcher: {(w.stdout or '').strip()}")
    return True


def dispatch(name, marker):
    # re-entry guard: a live session is never re-dispatched
    rec = dw._find(name)
    if rec and rec.get("action") not in TERMINAL:
        log(f"{name}: already live in registry (action={rec.get('action')}) — "
            f"re-arming watcher only")
        arm_watcher(name, marker)
        return True
    prompt = os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")
    if not os.path.exists(prompt):
        log(f"FATAL {name}: prompt missing at {prompt}")
        outbox(f"[TL1] DISPATCH ABORTED for {name} — packet {prompt} missing; "
               f"the Lead is re-authoring after the sandbox reset.")
        return False
    log(f"dispatching {name} (create)…")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt],
        cwd=BASE, timeout=1800, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    log(f"{name} create rc={r.returncode} tail={tail}")
    if r.returncode != 0:
        outbox(f"[TL1] {name} dispatch FAILED (rc={r.returncode}) — see "
               f"logs/tl1_dispatch.log; the Lead will re-fire it.")
        return False
    arm_watcher(name, marker)
    outbox(f"[TL1] {name.upper()} DISPATCHED from inside the replay — watcher "
           f"armed (marker: {marker}).")
    return True


def main():
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    started = time.time()
    log("TL1 sentinel up — waiting for operator chat.z.ai login "
        "(read-only polls; will not re-arm the usage-limit window)")
    outbox("[TL1] Replay redeployed after sandbox reset #5. Waiting for your "
           "chat.z.ai login through the console image — on login I dispatch "
           "the TL1 first sprint (tl1-a-001 / tl1-b-002 / tl1-c-003) from "
           "inside the replay. — TL1")
    while True:
        if login_state():
            log("LOGIN DETECTED — firing the TL1 first-sprint dispatch plan (3 slots)")
            outbox("[TL1] OPERATOR LOGIN DETECTED — dispatching the TL1 first "
                   "sprint now (3 slots, sequential).")
            break
        if time.time() - started > MAX_WAIT_SECS:
            log("gave up after 6h — exiting")
            outbox("[TL1] 6h login window expired — sentinel standing down; "
                   "ping the Lead to re-arm when you're back.")
            return 1
        time.sleep(POLL_SECS)
    ok = 0
    for name, marker in SESSIONS:
        if dispatch(name, marker):
            ok += 1
        else:
            log(f"{name} dispatch FAILED — continuing with the rest")
        time.sleep(20)
    log(f"TL1 dispatch round complete: {ok}/{len(SESSIONS)} live; watchers armed")
    outbox(f"[TL1] First-sprint dispatch round complete: {ok}/3 live, "
           f"queue_watch watchers armed. tl1-a-004 queued next (3-slot cap).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
