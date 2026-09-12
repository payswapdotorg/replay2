#!/usr/bin/env python3
"""auto_dispatch_after_login.py — sentinel that resumes worker dispatch the
instant the operator completes the chat.z.ai login (post-reboot fresh
browser profile).

Context (2026-09-12 16:15): the 15:59 machine reboot wiped the browser
profile; the ONLY unrecoverable item is the operator's chat.z.ai login
(via the replay console image). This sentinel polls the login state with
read-only DOM probes (never re-arms the usage-limit window, lesson 69),
then on login:
  1. dispatch rwo-001, rwo-003, vwo-011 (sequential creates, full assault
     machinery incl. sandbox-limit release handling) — the pre-reboot
     3-slot plan (rwo-002 queued next, cap = 3);
  2. arm one queue_watch watcher per session (launch_queue_watch);
  3. log everything to scripts/logs/auto_dispatch.log and exit.

Usage: auto_dispatch_after_login.py   (run detached via launch_detached.py)
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "auto_dispatch.log")
POLL_SECS = 45
MAX_WAIT_SECS = 6 * 3600  # give up after 6h (operator may be away)

SESSIONS = [
    ("rwo-001", "RWO-001 COMPLETION REPORT"),
    ("rwo-003", "RWO-003 COMPLETION REPORT"),
    ("vwo-011", "VWO-011 COMPLETION REPORT"),
]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


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
        t = channel.new_tab("https://chat.z.ai/")
        time.sleep(4)
        return False
    except Exception as e:
        log(f"login probe error {type(e).__name__} — retrying")
        return False


def dispatch(name, marker):
    prompt = os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")
    if not os.path.exists(prompt):
        log(f"FATAL {name}: prompt missing at {prompt}")
        return False
    log(f"dispatching {name} (create)…")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt],
        cwd=BASE, timeout=1800, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    log(f"{name} create rc={r.returncode} tail={tail}")
    if r.returncode != 0:
        return False
    # arm the watcher
    rec = dw._find(name)
    tab = (rec.get("tab_id") or "")[:8] if rec else ""
    if not tab:
        log(f"{name}: no registry tab — watcher NOT armed")
        return False
    w = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_queue_watch.py"), name, tab, marker],
        cwd=BASE, timeout=60, capture_output=True, text=True)
    log(f"{name} watcher: {w.stdout.strip()}")
    return True


def main():
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    started = time.time()
    log("sentinel up — waiting for operator chat.z.ai login "
        "(read-only polls; will not re-arm the usage-limit window)")
    while True:
        if login_state():
            log("LOGIN DETECTED — resuming dispatch plan (3 slots)")
            break
        if time.time() - started > MAX_WAIT_SECS:
            log("gave up after 6h — exiting")
            return 1
        time.sleep(POLL_SECS)
    ok = 0
    for name, marker in SESSIONS:
        if dispatch(name, marker):
            ok += 1
        else:
            log(f"{name} dispatch FAILED — continuing with the rest")
        time.sleep(20)
    log(f"dispatch round complete: {ok}/{len(SESSIONS)} live; watchers armed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
