#!/usr/bin/env python3
"""tradrl_login_watch.py — resident login detector + TradRL frontier auto-dispatcher.

Reset #9 (2026-09-29 ~12:31 UTC) destroyed the replay deployment AND the durable
operator JWT had already expired server-side; guest agent path dead site-side.
This daemon polls the replay browser (CDP :9222) every 45s for an AUTHENTICATED
chat.z.ai tab (sidebar Agent nav marker — the exact capability dispatch needs),
requires TWO consecutive positives (debounce), then:

  1. writes flags/login_confirmed.json
  2. extracts localStorage.token -> flags/chat_token (forensics rail, mode 600)
  3. sends an outbox note
  4. dispatches the live frontier (T030, T031, T043) via dispatch_worker.py
     create, substituting __GITHUB_PAT__ with the real PAT from env at send
     time (never written to disk in cleartext, never committed)
  5. on success per task writes flags/<task>_autodispatched.json; exits 0 when
     all three are live (or definitively rejected); retries failed ones next
     cycle (max 30 attempts each).

One-shot per frontier. No sandbox releases performed here (dispatch_worker's
built-in concurrency handling respects the live-session registry).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PROMPTS = os.path.join(BASE, "worker-prompts")
FRONTIER = ["T030", "T031", "T043"]  # wave-26 recovery (D-022/D-023 era; re-entry T030/T043 + fresh T031)

from dispatch_worker import JS_AGENT_PRESENT  # noqa: E402

POLL_S = 45
NEED_CONSECUTIVE = 2
MAX_ATTEMPTS = 30

os.makedirs(FLAGS, exist_ok=True)


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)


def chat_tabs():
    try:
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
    except Exception as e:
        log("CDP /json unavailable: %s" % e)
        return []
    return [t for t in tabs if t.get("type") == "page" and "chat.z.ai" in t.get("url", "")]


def agent_nav_present(tab):
    """True if this tab shows the authenticated shell (sidebar Agent nav)."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        r = c.call("Runtime.evaluate",
                   {"expression": JS_AGENT_PRESENT, "returnByValue": True},
                   timeout=30)
        return r.get("result", {}).get("value") == "found"
    except Exception as e:
        log("agent-nav probe error: %s" % e)
        return False


def extract_token(tab):
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        r = c.call("Runtime.evaluate",
                   {"expression": "localStorage.getItem('token')", "returnByValue": True},
                   timeout=30)
        return r.get("result", {}).get("value")
    except Exception as e:
        log("token extract error: %s" % e)
        return None


def outbox(note):
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "note": note}) + "\n")
    except Exception as e:
        log("outbox write failed: %s" % e)


def dispatched_flag(task):
    return os.path.join(FLAGS, "%s_autodispatched.json" % task)


def _arm_queue_watch(task):
    """Read the registry record for <task>, arm a detached queue_watch."""
    try:
        rec = None
        reg = os.path.join(FLAGS, "session_registry.jsonl")
        if os.path.isfile(reg):
            for line in open(reg, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("name") == task and r.get("tab_id"):
                    rec = r
        if not rec:
            log("%s: no registry record with tab_id — watcher NOT armed" % task)
            return
        tab_prefix = (rec.get("tab_id") or "")[:8]
        marker = "%s COMPLETION REPORT" % task
        ar = subprocess.run(
            [sys.executable, os.path.join(BASE, "launch_queue_watch.py"),
             task, tab_prefix, marker],
            cwd=BASE, capture_output=True, text=True, timeout=60)
        log("%s: queue_watch armed: %s" % (task, (ar.stdout or "").strip()[:120]))
    except Exception as e:
        log("%s: watcher arming failed: %s" % (task, e))


def dispatch_task(task):
    """Substitute PAT into the packet, dispatch via dispatch_worker create."""
    src = os.path.join(PROMPTS, "%s.md" % task)
    if not os.path.isfile(src):
        log("%s: prompt file missing: %s" % (task, src))
        return "no-prompt"
    body = open(src, encoding="utf-8").read()
    pat = os.environ.get("GITHUB_PAT", "")
    if "__GITHUB_PAT__" in body and not pat:
        log("%s: __GITHUB_PAT__ placeholder present but GITHUB_PAT env unset" % task)
        return "no-pat"
    body = body.replace("__GITHUB_PAT__", pat)
    fd, tmp = tempfile.mkstemp(prefix="pkt_%s_" % task, suffix=".md", dir=FLAGS)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(tmp, 0o600)
    try:
        log("%s: dispatching (create)…" % task)
        p = subprocess.run(
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "create", task, tmp],
            capture_output=True, text=True, timeout=900)
        out = (p.stdout or "") + (p.stderr or "")
        log("%s: create rc=%s tail=%s" % (task, p.returncode, out[-500:].replace("\n", " | ")))
        if p.returncode == 0:
            with open(dispatched_flag(task), "w") as f:
                json.dump({"task": task, "ts": time.time(), "rc": 0}, f)
            outbox("frontier auto-dispatch: %s create OK" % task)
            _arm_queue_watch(task)
            return "ok"
        return "rc=%s" % p.returncode
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main():
    consecutive = 0
    attempts = {t: 0 for t in FRONTIER}
    log("resident: polling CDP :9222 every %ss for authenticated chat.z.ai tab" % POLL_S)
    while True:
        todo = [t for t in FRONTIER if not os.path.exists(dispatched_flag(t))]
        if not todo:
            log("all frontier tasks dispatched — exiting 0")
            return 0
        tabs = chat_tabs()
        auth_tab = None
        for t in tabs:
            if agent_nav_present(t):
                auth_tab = t
                break
        if auth_tab is None:
            consecutive = 0
            log("not authenticated (%d chat tabs, %d frontier pending)" % (len(tabs), len(todo)))
            time.sleep(POLL_S)
            continue
        consecutive += 1
        log("authenticated tab detected (%d/%d)" % (consecutive, NEED_CONSECUTIVE))
        if consecutive < NEED_CONSECUTIVE:
            time.sleep(POLL_S)
            continue
        # confirmed
        with open(os.path.join(FLAGS, "login_confirmed.json"), "w") as f:
            json.dump({"ts": time.time(), "tab": auth_tab["id"]}, f)
        tok = extract_token(auth_tab)
        if tok:
            tf = os.path.join(FLAGS, "chat_token")
            with open(tf, "w") as f:
                f.write(tok)
            os.chmod(tf, 0o600)
        outbox("operator login confirmed (watcher %s)" % time.strftime("%H:%M:%S"))
        log("LOGIN CONFIRMED — dispatching frontier: %s" % ",".join(todo))
        for task in todo:
            if attempts[task] >= MAX_ATTEMPTS:
                log("%s: max attempts reached — leaving for the Lead" % task)
                continue
            attempts[task] += 1
            res = dispatch_task(task)
            if res != "ok":
                log("%s: dispatch failed (%s) — will retry next cycle (attempt %d/%d)"
                    % (task, res, attempts[task], MAX_ATTEMPTS))
        # after a dispatch round, keep polling in case some tasks failed;
        # if everything succeeded the loop head exits.
        if all(os.path.exists(dispatched_flag(t)) for t in FRONTIER):
            log("frontier fully dispatched — exiting 0")
            return 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
