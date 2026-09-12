#!/usr/bin/env python3
"""suspension_lift_sentinel.py — polls the suspended chat.z.ai account and
auto-resumes the 3-slot dispatch plan the moment access is restored.

Context (2026-09-12 16:20): minutes after the operator's post-reboot login
(rwo-003 dispatched successfully at 16:17), the account hit a SUSPENSION
wall ("Your account has been suspended / Access will be restored after
9/19/2026, 4:17:35 PM") — verified IP-independent (VPN on/off) and
account-wide (chats API 403; the parallel lineage's last commit is create()
crash-recovery for the same wall). rwo-003's turn died mid-clone (zombie).

On lift (suspension text gone + still logged in):
  void rwo-001 + rwo-003 (stale/zombie records) -> fresh create
  rwo-001, rwo-003, vwo-011 -> arm watchers -> exit.
If the login was also invalidated by the suspension, keep polling and note
it in the log (the operator must re-login; the auto_dispatch sentinel
pattern then takes over via the login-state check here too).

Usage: run detached. Poll cadence 300s (read-only reload of the error tab).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "suspension_lift.log")
POLL_SECS = 300
MAX_WAIT_SECS = 8 * 24 * 3600

SESSIONS = [
    ("rwo-001", "RWO-001 COMPLETION REPORT"),
    ("rwo-003", "RWO-003 COMPLETION REPORT"),
    ("vwo-011", "VWO-011 COMPLETION REPORT"),
]


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def probe():
    """Reload the chat.z.ai home tab; classify: suspended / logged-out /
    open (access restored)."""
    try:
        tabs = channel.list_tabs()
        t = None
        for x in tabs:
            u = x.get("url") or ""
            if u.startswith("https://chat.z.ai") and "/c/" not in u and "chrome-ext" not in u:
                t = x
                break
        if not t:
            t = channel.new_tab("https://chat.z.ai/")
            time.sleep(5)
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
        c.call("Page.enable")
        c.call("Page.reload")
        time.sleep(7)
        url = dw._eval(c, "location.href", timeout=10) or ""
        body = dw._eval(c, "document.body.innerText || ''", timeout=25) or ""
        c.close()
        if "suspended" in body.lower():
            return "suspended", url, body
        if "Sign in" in body or "Log in" in body:
            return "logged-out", url, body
        return "open", url, body
    except Exception as e:
        return f"error:{type(e).__name__}", "", ""


def dispatch(name, marker):
    prompt = os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")
    if not os.path.exists(prompt):
        log(f"FATAL {name}: prompt missing")
        return False
    rec = dw._find(name)
    if rec and rec.get("url"):
        subprocess.run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                        "void", name, "suspension-lift fresh re-dispatch"],
                       cwd=BASE, timeout=300, capture_output=True, text=True)
    log(f"dispatching {name}…")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt],
        cwd=BASE, timeout=1800, capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-2:]
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
    started = time.time()
    last_state = None
    while True:
        st, url, body = probe()
        if st != last_state:
            log(f"state={st} url={url[:60]} body-head={body[:120].replace(chr(10), ' | ')}")
            last_state = st
        if st == "open":
            log("ACCESS RESTORED — resuming the 3-slot dispatch plan")
            break
        if st == "logged-out":
            log("suspension lifted but logged out — operator re-login needed; keeping watch")
        if time.time() - started > MAX_WAIT_SECS:
            log("gave up after 8 days")
            return 1
        time.sleep(POLL_SECS)
    ok = 0
    for name, marker in SESSIONS:
        if dispatch(name, marker):
            ok += 1
        time.sleep(20)
    log(f"dispatch round complete: {ok}/{len(SESSIONS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
