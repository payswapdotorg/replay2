#!/usr/bin/env python3
"""restore_zai_session.py — restore chat.z.ai authentication into the replay
browser from the durable token file (recycle-proof session restore).

THE BARE-TOKEN LAW (discovered 2026-10-03, recycle #7): chat.z.ai stores its
JWT in localStorage['token'] BARE (unquoted). Injecting it JSON-quoted makes
the SPA treat it as invalid and silently mint a guest session. The defensive
quote-stripping in the extraction code (bridge._login_state) masked this.

The token itself is validated server-side (Bearer header works on
/api/v1/chats/list even when the SPA has fallen back to guest), so the
durable capture stays useful across recycles.

Usage: python3 restore_zai_session.py [token-file]
Default token file: /home/z/my-project/download/zai_session_token.txt
Exit 0 = authenticated as a real (non-guest) account; 1 = failure.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "replay2", "scripts"))
try:
    import channel
except ImportError:
    sys.exit("no channel.py — is the replay stack deployed?")

DEFAULT_TOKEN = "/home/z/my-project/download/zai_session_token.txt"
FLAGS = "/home/z/replay2/scripts/flags"


def pages():
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        return [t for t in json.load(r) if t.get("type") == "page"]


def identity(cdp):
    return cdp.eval(
        "(function(){try{var t=(localStorage.getItem('token')||'')"
        ".replace(/^\"|\"$/g,'');"
        "var p=JSON.parse(atob(t.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')));"
        "return p.email||p.sub||'?'}catch(e){return 'parse-fail'}})()",
        await_promise=False, timeout=8)


def main():
    tokfile = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOKEN
    tok = open(tokfile).read().strip()
    if not tok or tok.count(".") < 2:
        print("invalid token file:", tokfile)
        return 1

    # refresh the orchestration token cache too (kick_queued/lane_status read it)
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(os.path.join(FLAGS, "chat_token"), "w") as f:
            f.write(tok)
        os.chmod(os.path.join(FLAGS, "chat_token"), 0o600)
    except Exception:
        pass

    tabs = [t for t in pages() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        req = urllib.request.Request(
            "http://localhost:9222/json/new?https://chat.z.ai/", method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            tabs = [json.load(r)]
        time.sleep(4)
    tab = tabs[0]
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
    tab = next((t for t in pages() if "chat.z.ai" in (t.get("url") or "")), None)
    if not tab:
        print("no chat.z.ai tab after navigation")
        return 1
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        for _ in range(24):
            if c.eval("document.readyState", await_promise=False,
                      timeout=5) == "complete":
                break
            time.sleep(0.5)
        time.sleep(4)
        ident = identity(c)
        print("identity:", ident)
        if ident.startswith("guest-"):
            print("TOKEN REJECTED — server-side session likely rotated; "
                  "operator manual re-login required (slider-captcha path)")
            return 1
        print("SESSION RESTORED:", ident)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
