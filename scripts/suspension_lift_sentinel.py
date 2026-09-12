#!/usr/bin/env python3
"""suspension_lift_sentinel.py — polls the suspended chat.z.ai account and
auto-resumes the 3-slot dispatch plan the moment access is restored.

Context (2026-09-12 16:20): minutes after the operator's post-reboot login
(rwo-003 dispatched successfully at 16:17), the account hit a SUSPENSION
wall ("Your account has been suspended / Access will be restored after
9/19/2026, 4:17:35 PM") — verified IP-independent (VPN on/off) and
account-wide (chats API 403; the parallel lineage's last commit is create()
crash-recovery for the same wall). rwo-003's turn died mid-clone (zombie).

HARDENING (original hotfix 9255580, 2026-09-12 17:26 — never pushed; ported
from the handoff description after the sandbox reset): the unhardened probe
classified ANY page that was neither "suspended" nor "Sign in" as OPEN —
including chrome-error:// net-error pages — and fired the dispatch plan on
a SINGLE probe (misfired exactly this way at 16:26 during a transient
net-error; held fire correctly at 17:21→17:26 after hardening). Now:
  1. chrome-error:// pages, net-error body markers, blank shells and URLs
     that never landed on chat.z.ai classify as net-error — NEVER open;
  2. the plan fires only after TWO CONSECUTIVE genuine open probes
     (>=600s of confirmed openness at the 300s cadence);
  3. a 0/3 dispatch round RESUMES WATCHING (600s cooldown) instead of
     exiting; after three consecutive 0/3 rounds the cadence backs off to
     1800s (batch retries, never grind — lesson 40 posture).

On lift (two consecutive genuine open probes, still logged in):
  void rwo-001 + rwo-003 (stale/zombie records) -> fresh create
  rwo-001, rwo-003, vwo-011 -> arm watchers -> exit.
If the login was also invalidated by the suspension, keep polling and note
it in the log (the operator must re-login; the auto_dispatch sentinel
pattern then takes over via the login-state check here too).

Usage: run detached via scripts/launch_detached.py. Poll cadence 300s
(read-only reload of the home tab).
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
RESUME_POLL_SECS = 600          # 0/3 round: resume watching, slower cadence
BACKOFF_POLL_SECS = 1800        # 3 consecutive 0/3 rounds: batch, never grind
MAX_WAIT_SECS = 8 * 24 * 3600
OPEN_STREAK_REQUIRED = 2        # two consecutive GENUINE open probes

SESSIONS = [
    ("rwo-001", "RWO-001 COMPLETION REPORT"),
    ("rwo-003", "RWO-003 COMPLETION REPORT"),
    ("vwo-011", "VWO-011 COMPLETION REPORT"),
]

NET_ERR_MARKERS = (
    "chrome-error://",
    "This site can’t be reached",
    "This site can't be reached",
    "aw, snap",
    "err_",
    "err internet",
    "network changed",
    "connection was reset",
    "connection has been reset",
    "webpage is not available",
    "took too long to respond",
    "no internet",
)


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def probe():
    """Reload the chat.z.ai home tab; classify: suspended / logged-out /
    open (access restored) / net-error / error:<ExcType>.

    HARDENING: a chrome-error:// page is a NET ERROR, not a lift. "open"
    requires the tab to actually BE on chat.z.ai with a rendered body and
    no suspension / sign-in / net-error text.
    """
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
        if "chrome-error" in url:
            return "net-error", url, body
        if "suspended" in body.lower():
            return "suspended", url, body
        low = body.lower()
        if any(m in low for m in NET_ERR_MARKERS):
            return "net-error", url, body
        if "Sign in" in body or "Log in" in body:
            return "logged-out", url, body
        if "chat.z.ai" not in url:
            return "net-error", url, body
        if len(body.strip()) < 200:
            # blank/empty shell — no positive proof of a rendered app
            return "net-error", url, body
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


def watch(poll, started):
    """Watch phase: poll until TWO CONSECUTIVE genuine open probes.
    Returns True when access is confirmed restored, False on give-up."""
    last_state = None
    open_streak = 0
    while True:
        st, url, body = probe()
        if st != last_state:
            log(f"state={st} url={url[:60]} body-head={body[:120].replace(chr(10), ' | ')}")
            last_state = st
        if st == "open":
            open_streak += 1
            log(f"genuine open probe {open_streak}/{OPEN_STREAK_REQUIRED}")
            if open_streak >= OPEN_STREAK_REQUIRED:
                return True
        else:
            if open_streak:
                log(f"open streak broken by state={st} — resetting "
                    f"(a net-error page is NOT a lift)")
            open_streak = 0
        if st == "logged-out":
            log("login state lost (or unclear) — operator re-login may be needed; keeping watch")
        if time.time() - started > MAX_WAIT_SECS:
            log("gave up after 8 days")
            return False
        time.sleep(poll)


def main():
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    started = time.time()
    poll = POLL_SECS
    zero_rounds = 0
    while True:
        if not watch(poll, started):
            return 1
        log("ACCESS RESTORED (confirmed x%d) — resuming the 3-slot dispatch plan"
            % OPEN_STREAK_REQUIRED)
        ok = 0
        for name, marker in SESSIONS:
            if dispatch(name, marker):
                ok += 1
            time.sleep(20)
        log(f"dispatch round complete: {ok}/{len(SESSIONS)}")
        if ok > 0:
            return 0
        zero_rounds += 1
        if zero_rounds >= 3:
            poll = BACKOFF_POLL_SECS
            log("three consecutive 0/3 rounds — backing off to "
                f"{BACKOFF_POLL_SECS}s cadence (batch, never grind)")
        else:
            poll = RESUME_POLL_SECS
        log(f"0/{len(SESSIONS)} round — resuming watch (cadence {poll}s) "
            "before re-confirming and retrying")


if __name__ == "__main__":
    sys.exit(main())
