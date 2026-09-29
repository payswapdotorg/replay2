#!/usr/bin/env python3
"""login_watch_dispatch.py — resident login detector + W090C auto-dispatcher.

Context (2026-09-29, reset #9): the durable operator JWT expired server-side and
the site no longer provisions guest agent sessions (3 probes: the guest landing
has NO sidebar Agent nav). W090C is the only remaining Wave 8 worker item and is
queued on operator login through the replay console (:3000).

The TL session is dormant between operator messages; with a midnight deadline
this daemon closes the gap: it polls the replay browser (CDP :9222) every 60s
for an AUTHENTICATED chat.z.ai tab (the sidebar Agent nav marker — the exact
capability dispatch needs), requires TWO consecutive positives (debounce), then:

  1. writes flags/login_confirmed.json  (the resident watcher's login flag flips)
  2. extracts localStorage.token -> flags/chat_token (forensics rail, mode 600)
  3. sends an outbox note
  4. immediately dispatches W090C via dispatch_worker.py create (which contains
     the aggressive capacity-fight loop) — dispatch from INSIDE the replay per
     the standing operator directive
  5. on success writes flags/w090c_autodispatched.json and exits 0;
     on failure logs and retries next cycle (max 20 attempts).

No sandbox releases are performed here (dispatch_worker's built-in concurrency
handling respects the live-session registry). One-shot: exits after dispatch.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
DONE_FLAG = os.path.join(FLAGS, "w090c_autodispatched.json")
PROMPT = "/home/z/my-project/wave8-prompts/W090C.md"

from dispatch_worker import JS_AGENT_PRESENT  # noqa: E402

POLL_S = 60
NEED_CONSECUTIVE = 2
MAX_ATTEMPTS = 20


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
                   {"expression": "localStorage.getItem('token') || ''",
                    "returnByValue": True},
                   timeout=30)
        return str(r.get("result", {}).get("value") or "")
    except Exception as e:
        log("token extract error: %s" % e)
        return ""


def outbox(note):
    os.makedirs(FLAGS, exist_ok=True)
    rec = {"ts": int(time.time()), "from": "resident-td", "note": note}
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log("outbox write failed: %s" % e)


def registry_has_live_w090c():
    """True if the registry's latest w090c create record is still valid."""
    if not os.path.exists(REG):
        return False
    live = False
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("name") != "w090c":
                    continue
                if rec.get("action") == "create":
                    live = True
                elif rec.get("action") in ("void", "failed"):
                    live = False
    except Exception:
        return False
    return live


def main():
    os.makedirs(FLAGS, exist_ok=True)
    if os.path.exists(DONE_FLAG):
        log("w090c already auto-dispatched — exiting")
        return 0
    log("login-watch armed: polling every %ss for authenticated chat.z.ai tab; "
        "will auto-dispatch W090C on login" % POLL_S)
    consecutive = 0
    attempts = 0
    while True:
        auth_tabs = [t for t in chat_tabs() if agent_nav_present(t)]
        if auth_tabs:
            consecutive += 1
            log("authenticated shell visible (%d/%d)" % (consecutive, NEED_CONSECUTIVE))
        else:
            if consecutive:
                log("authenticated state lost — resetting debounce")
            consecutive = 0
        if consecutive >= NEED_CONSECUTIVE:
            break
        time.sleep(POLL_S)

    tab = auth_tabs[0]
    log("OPERATOR LOGIN CONFIRMED on tab %s (%s)" % (tab.get("id"), tab.get("url")))

    # 1. login flag (flips the resident watcher to LOGGED-IN)
    with open(os.path.join(FLAGS, "login_confirmed.json"), "w") as f:
        json.dump({"method": "operator-login-detected", "ts": int(time.time()),
                   "tab": tab.get("id"), "url": tab.get("url")}, f)
    # 2. forensics rail: durable copy of the fresh session token
    tok = extract_token(tab)
    if tok:
        with open(os.path.join(FLAGS, "chat_token"), "w") as f:
            f.write(tok)
        os.chmod(os.path.join(FLAGS, "chat_token"), 0o600)
        log("chat_token captured (%d chars)" % len(tok))
    # 3. outbox note
    outbox("Operator login detected on the replay image. W090C auto-dispatch "
           "engaged immediately (the last Wave 8 worker item; dispatch from "
           "inside the replay per the standing directive).")

    # 4. dispatch W090C (unless a live registry record already exists)
    while attempts < MAX_ATTEMPTS:
        if os.path.exists(DONE_FLAG):
            log("done-flag appeared — exiting")
            return 0
        if registry_has_live_w090c():
            log("registry already holds a live w090c create record — not re-dispatching")
            with open(DONE_FLAG, "w") as f:
                json.dump({"ts": int(time.time()), "reason": "registry-live"}, f)
            return 0
        attempts += 1
        log("dispatch attempt %d/%d: create w090c" % (attempts, MAX_ATTEMPTS))
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                 "create", "w090c", PROMPT],
                capture_output=True, text=True, timeout=900, cwd=BASE)
            tail = "\n".join((r.stdout or "").splitlines()[-6:])
            log("create rc=%d tail:\n%s" % (r.returncode, tail))
            if r.returncode == 0:
                with open(DONE_FLAG, "w") as f:
                    json.dump({"ts": int(time.time()), "attempts": attempts}, f)
                outbox("W090C dispatched successfully by the login-watch daemon "
                       "(attempt %d). TL harvest on work/w090c push." % attempts)
                log("W090C DISPATCHED — exiting")
                return 0
        except subprocess.TimeoutExpired:
            log("create timed out (900s) — will retry")
        except Exception as e:
            log("create error: %s — will retry" % e)
        time.sleep(POLL_S)
    outbox("W090C auto-dispatch exhausted %d attempts without success — "
           "TL manual dispatch required on next active session." % MAX_ATTEMPTS)
    log("giving up after %d attempts" % MAX_ATTEMPTS)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
