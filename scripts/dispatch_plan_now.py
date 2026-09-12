#!/usr/bin/env python3
"""dispatch_plan_now.py — dispatch the standing 3-slot codex plan directly.

The suspension_lift_sentinel's dispatch logic, minus the probe-wait: the
Lead has POSITIVELY verified account access (operator logged in; chats API
200 with live data; workspaces API harvested 665 files through it), so the
two-consecutive-probe caution is unnecessary. Sequential creates with full
assault machinery (incl. sandbox-limit release), then one queue_watch
watcher per session. Idempotent per name (skips if a live registry record
with a URL already exists).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dispatch_worker as dw  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "dispatch_plan_now.log")

SESSIONS = [
    ("rwo-001", "RWO-001 COMPLETION REPORT"),
    ("rwo-003", "RWO-003 COMPLETION REPORT"),
    ("vwo-011", "VWO-011 COMPLETION REPORT"),
]


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def dispatch(name, marker):
    prompt = os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")
    if not os.path.exists(prompt):
        log(f"FATAL {name}: prompt missing at {prompt}")
        return False
    rec = dw._find(name)
    if rec and rec.get("url"):
        log(f"{name}: registry already has a live record ({rec.get('url','')[:50]}) — skipping")
        return True
    log(f"dispatching {name} (create)…")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt],
        cwd=BASE, timeout=1800, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    log(f"{name} create rc={r.returncode} tail={tail}")
    if r.returncode != 0:
        return False
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
    ok = 0
    for name, marker in SESSIONS:
        if dispatch(name, marker):
            ok += 1
        time.sleep(20)
    log(f"dispatch round complete: {ok}/{len(SESSIONS)}")
    return 0 if ok == len(SESSIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
