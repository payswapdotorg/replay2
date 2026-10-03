#!/usr/bin/env python3
"""login_keeper.py — keep the replay browser's chat.z.ai session alive,
captured and durable (rebuilt 2026-10-03 after reset-4; D-034 lesson baked
in: CDP/WS hiccups are logged and skipped — NEVER fatal).

Duties (cycle every 60s):
  - heartbeat flags/login_keeper_hb.txt
  - read the browser login state (localStorage['token'] BARE — the
    BARE-TOKEN law; identity = JWT email claim, guest- prefix = not
    authenticated)
  - AUTHENTICATED: every 20 min, snapshot the token to the DURABLE file
    /home/z/my-project/download/zai_session_token.txt (my-project volume
    survives rootfs resets) + flags/chat_token (orchestration cache).
    Log "[login_keeper HH:MM:SS] snapshot saved (<identity>)".
  - NOT authenticated (fresh/reset browser): restore-pass — if the durable
    token file exists, inject it (restore_zai_session.py semantics: clear
    localStorage, set bare token, reload) with a bounded retry loop; if no
    durable file, log the wait state (operator must log in through the
    console once; the keeper captures it the moment it lands).

Launch: dfork_launch.py /tmp/login_keeper.log <py> login_keeper.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
HB = os.path.join(FLAGS, "login_keeper_hb.txt")
CHAT_TOKEN = os.path.join(FLAGS, "chat_token")
DURABLE = "/home/z/my-project/download/zai_session_token.txt"

POLL = 60
SNAPSHOT_EVERY = 1200  # 20 min
RESTORE_RETRY = 6      # restore-pass attempts per not-logged-in episode


def log(msg):
    print(f"[login_keeper {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def pages():
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        return [t for t in json.load(r) if t.get("type") == "page"]


def chat_tab():
    tabs = [t for t in pages() if "chat.z.ai" in (t.get("url") or "")]
    return tabs[0] if tabs else None


def ensure_chat_tab():
    """Open a chat.z.ai tab if none exists (fresh browser post-reset)."""
    if chat_tab() is not None:
        return True
    try:
        req = urllib.request.Request(
            "http://localhost:9222/json/new?https://chat.z.ai/", method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            json.load(r)
        time.sleep(4)
        return chat_tab() is not None
    except Exception as e:
        log(f"tab-open failed: {e}")
        return False


def login_state():
    """(token, identity) via CDP; (None, reason) on failure (never raises —
    D-034: a 2.5h keeper death came from one uncaught WS timeout)."""
    try:
        tab = chat_tab()
        if tab is None:
            return None, "no-tab"
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            tok = c.eval(
                "(localStorage.getItem('token')||'')"
                ".replace(/^\"|\"$/g,'')",
                await_promise=False, timeout=8) or ""
            ident = c.eval(
                "(function(){try{var t=(localStorage.getItem('token')||'')"
                ".replace(/^\"|\"$/g,'');"
                "var p=JSON.parse(atob(t.split('.')[1].replace(/-/g,'+')"
                ".replace(/_/g,'/')));"
                "return p.email||p.sub||'?'}catch(e){return 'parse-fail'}})()",
                await_promise=False, timeout=8)
            return (tok or None), (ident or "?")
        finally:
            c.close()
    except Exception as e:
        return None, f"cdp-error: {type(e).__name__}"


def save_snapshot(tok, ident):
    try:
        os.makedirs(os.path.dirname(DURABLE), exist_ok=True)
        with open(DURABLE, "w") as f:
            f.write(tok)
        os.chmod(DURABLE, 0o600)
        with open(CHAT_TOKEN, "w") as f:
            f.write(tok)
        os.chmod(CHAT_TOKEN, 0o600)
        log(f"snapshot saved ({ident})")
        return True
    except OSError as e:
        log(f"snapshot save failed: {e}")
        return False


def restore_pass():
    """Inject the durable token into a logged-out browser (bare, never
    JSON-quoted). Bounded retries; every step guarded (D-034)."""
    if not os.path.exists(DURABLE):
        return False
    try:
        tok = open(DURABLE).read().strip()
    except OSError:
        return False
    if not tok or tok.count(".") < 2:
        return False
    for attempt in range(1, RESTORE_RETRY + 1):
        try:
            tab = chat_tab()
            if tab is None:
                if not ensure_chat_tab():
                    time.sleep(10)
                    continue
                tab = chat_tab()
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
            try:
                c.eval("localStorage.clear()", await_promise=False, timeout=8)
                # THE LAW: bare, never JSON-quoted
                c.eval("localStorage.setItem('token', %s)" % json.dumps(tok),
                       await_promise=False, timeout=8)
                c.eval("location.href='https://chat.z.ai/'",
                       await_promise=False, timeout=8)
            finally:
                c.close()
            time.sleep(10)
            _tok, ident = login_state()
            if _tok and not str(ident).startswith("guest-"):
                log(f"SESSION RESTORED from durable token ({ident})")
                with open(CHAT_TOKEN, "w") as f:
                    f.write(tok)
                return True
            log(f"restore attempt {attempt}: identity={ident} — retrying")
        except Exception as e:
            log(f"restore attempt {attempt} failed: {type(e).__name__}: {e}")
        time.sleep(15)
    log("restore-pass exhausted — token rejected (session rotated); "
        "operator manual re-login required (console slider-captcha path)")
    return False


def main():
    log("armed — 60s cycles, 20-min snapshots, durable file "
        + DURABLE)
    last_snap = 0.0
    restored = False
    while True:
        try:
            open(HB, "w").write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except OSError:
            pass

        try:
            tok, ident = login_state()
        except Exception as e:  # belt-and-braces (D-034)
            log(f"login_state top-level guard: {e}")
            tok, ident = None, "error"

        if tok and not str(ident).startswith("guest-") and ident != "parse-fail":
            restored = False  # a fresh manual login resets the episode
            if time.time() - last_snap >= SNAPSHOT_EVERY:
                if save_snapshot(tok, ident):
                    last_snap = time.time()
        else:
            last_snap = 0.0
            if not restored:
                log(f"browser not authenticated ({ident}) — attempting "
                    "restore-pass")
                restored = restore_pass()
                if not restored and not os.path.exists(DURABLE):
                    log("no durable token on file — waiting for operator "
                        "login through the console (:3000)")

        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
