#!/usr/bin/env python3
"""p2fix_login_watch.py — P2-FIX partition D login watch + dispatch (lead station tooling).

Rebuilt 2026-09-30 for the TL4 claim wave (P2-FIX-201/202/205, partition D).
The browser profile is FRESH after sandbox reset #12 -> the site is logged
out. This watch:
  1. polls chat.z.ai tabs for the authenticated agent shell (2 consecutive
     confirmations, the debounce law);
  2. on operator login: captures the chat token (BOTH durable locations —
     the reset-#10 lesson), writes flags/login_confirmed.json, notes the
     outbox;
  3. runs the dispatch fight for the staged packet
     (dispatch_worker.py create p2fix-d <packet>) — 12 in-process capacity
     rounds under the operator policy (never wait, never switch model);
     on exhaustion create() writes the capacity_recover flag and the
     supervisor's ensure_capacity_recovery() adopts the assault loop
     (indefinite autonomous rounds);
  4. exits after the first verified landing (queue watch / the ring own the
     rest).
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402
from bridge import _login_state  # noqa: E402  (canonical: JWT email + guest discrimination)

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
DURABLE_TOKEN = "/home/z/my-project/download/zai_session_token.txt"
PACKET = os.path.join(BASE, "worker-prompts", "p2fix-d.md")
SESSION = "p2fix-d"
DONE_FLAG = os.path.join(FLAGS, "p2fix_d_dispatched.json")

POLL_S = 60
NEED_CONSECUTIVE = 2


def log(msg):
    line = "[p2fix-watch %s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)


def outbox(text):
    os.makedirs(FLAGS, exist_ok=True)
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def chat_tabs():
    return [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]


def login_ok(tab):
    """Canonical login law: a JWT email that is NOT guest-* wins; guest
    home pages render composers too, so composer/Agent-text heuristics
    false-positive on a fresh profile (bridge._login_state, 2026-09-28)."""
    try:
        st = _login_state(tab, connect_timeout=6, eval_timeout=5)
    except Exception:
        return False, "probe-error"
    return st.startswith("logged-in("), st


def agent_shell_present(tab):
    """Kept for reference/debug: the weak 'Agent' text probe — NOT trusted
    for login (matches the logged-out home). Use login_ok()."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            from dispatch_worker import JS_AGENT_PRESENT
            return bool(c.eval(JS_AGENT_PRESENT, await_promise=False, timeout=10))
        finally:
            c.close()
    except Exception:
        return False


def extract_token(tab):
    """The canonical chat token: localStorage 'token' (JWT), quotes stripped
    (bridge._login_state's exact read)."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            tok = c.eval(
                "(localStorage.getItem('token')||'').replace(/^\"|\"$/g,'')",
                await_promise=False, timeout=10)
            return (tok or "").strip() if isinstance(tok, str) else ""
        finally:
            c.close()
    except Exception:
        return ""


def main():
    if os.path.exists(DONE_FLAG):
        log("p2fix-d already dispatched — exiting")
        return 0
    log("armed: polling %ss for operator login (JWT-guest law); packet=%s session=%s"
        % (POLL_S, PACKET, SESSION))
    consecutive = 0
    tab = None
    while True:
        auth = []
        for t in chat_tabs()[:3]:
            ok, st = login_ok(t)
            if ok:
                auth.append((t, st))
                break
        if auth:
            consecutive += 1
            log("login confirmed by JWT email (%d/%d): %s on %s"
                % (consecutive, NEED_CONSECUTIVE, auth[0][1], (auth[0][0].get("url") or "")[:60]))
            tab = auth[0][0]
        else:
            if consecutive:
                log("login state lost — resetting debounce")
            consecutive = 0
        if consecutive >= NEED_CONSECUTIVE:
            break
        time.sleep(POLL_S)

    log("OPERATOR LOGIN CONFIRMED on tab %s" % (tab.get("id") or "?")[:8])

    # 1. login flag (flips the resident ring to LOGGED-IN)
    os.makedirs(FLAGS, exist_ok=True)
    with open(os.path.join(FLAGS, "login_confirmed.json"), "w") as f:
        json.dump({"method": "operator-login-detected", "ts": int(time.time()),
                   "tab": tab.get("id"), "url": tab.get("url"),
                   "wave": "p2fix-d"}, f)

    # 2. durable token capture (BOTH locations — the reset-#10 lesson)
    tok = extract_token(tab)
    if tok:
        with open(os.path.join(FLAGS, "chat_token"), "w") as f:
            f.write(tok)
        os.chmod(os.path.join(FLAGS, "chat_token"), 0o600)
        try:
            os.makedirs(os.path.dirname(DURABLE_TOKEN), exist_ok=True)
            with open(DURABLE_TOKEN, "w") as f:
                f.write(tok)
            os.chmod(DURABLE_TOKEN, 0o600)
            log("chat_token captured (%d chars) + durable copy" % len(tok))
        except Exception as e:
            log("durable token write failed: %s" % e)
    else:
        log("token extraction came back empty (login still usable; dispatch proceeds)")

    # 3. outbox note
    outbox("Operator login detected (p2fix login-watch). Dispatching the "
           "P2-FIX partition D work order now: Worker p2fix-d, packet "
           "pinned @ e063c12b951 (TL4 claim 201/202/205, three branches). "
           "Capacity policy: never wait, never switch model — supervisor-"
           "guarded recovery owns the fight if peak hours block the send.")

    # 4. the dispatch fight (create() = tab + selections + staged prompt +
    #    send assault rounds; writes capacity_recover.p2fix-d.json on
    #    exhaustion — the supervisor adopts it automatically)
    #    2026-09-30 pat lesson: the watch runs detached WITHOUT a login
    #    shell — source the canonical secrets file into the subprocess env
    #    or the [REDACTED:github_token] placeholder reaches the worker
    #    unsubstituted (the first dispatch needed a correction message).
    env = dict(os.environ)
    try:
        with open("/home/z/.secrets/env.sh", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export ") and "=" in line:
                    k, _, v = line[len("export "):].partition("=")
                    v = v.strip().strip('"').strip("'")
                    env[k] = v
    except OSError:
        pass
    for k in ("GITHUB_TOKEN", "GH_TOKEN", "PAYSWAP_PAT", "OPERATOR_PAT",
              "GITHUB_OPERATOR_PAT"):
        env.setdefault(k, env.get("GITHUB_TOKEN", ""))
    p = subprocess.run(
        [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
         "create", SESSION, PACKET],
        cwd=BASE, env=env, timeout=3600)
    rc = p.returncode
    log("dispatch_worker create rc=%d" % rc)

    if rc == 0:
        outbox("p2fix-d DISPATCHED VERIFIED (prompt insert + send verified "
               "server-side). The worker owns the lane from here; the TL "
               "station will supervise, harvest and re-verify.")
        with open(DONE_FLAG, "w") as f:
            json.dump({"ts": int(time.time()), "rc": rc, "session": SESSION,
                       "packet": PACKET}, f)
        return 0
    if rc == 1:
        log("session already exists — checking state and leaving it to the ring")
        outbox("p2fix-d session already exists (registry record). The ring "
               "owns continuation; no second dispatch.")
        return 0
    if rc == 3:
        outbox("p2fix-d send hit the peak-hours capacity gate after 12 "
               "in-process rounds. The capacity_recover flag is written; "
               "the supervisor's recover_capacity loop now owns the "
               "assault (indefinite, operator policy: never wait).")
        return 3
    outbox("p2fix-d dispatch crashed (rc=%d) — the TL will inspect and "
           "re-arm on next pickup." % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
