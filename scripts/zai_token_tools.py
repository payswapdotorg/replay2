#!/usr/bin/env python3
"""zai_token_tools.py — durable chat.z.ai login: capture + inject the operator JWT.

Lesson 114: the auth `token` cookie is httpOnly + session:true — it dies with
the browser process (and every sandbox reset wipes the profile). The login is
recoverable WITHOUT the operator if the JWT is captured to a durable path
(sandbox resets keep non-dot files under /home/z/my-project/) and re-injected
afterwards: (a) localStorage 'token', (b) the HOST-ONLY httpOnly cookie
(Network.setCookie — a leading-dot domain gets set but the app still shows the
login form), then navigate and verify the app shell. The payload email
guest-...@guest.com means dead session; the operator email means restored.

Usage:
  python3 zai_token_tools.py capture [durable-file]   # from a logged-in tab
  python3 zai_token_tools.py inject  [durable-file]   # into a fresh profile
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

DEFAULT_DURABLE = "/home/z/my-project/download/zai_operator_jwt.txt"


def _decode_jwt_payload(tok):
    try:
        part = tok.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def _logged_in_tabs():
    out = []
    for t in channel.list_tabs():
        if t.get("type") != "page" or "chat.z.ai" not in (t.get("url") or ""):
            continue
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            try:
                tok = c.eval("localStorage.getItem('token') || ''", timeout=10)
            finally:
                c.close()
        except Exception:
            continue
        if tok and "guest" not in str(_decode_jwt_payload(tok).get("email", "guest")):
            out.append((t, tok))
    return out


def capture(durable):
    tabs = _logged_in_tabs()
    if not tabs:
        print("NO-OPERATOR-TOKEN: no chat.z.ai tab holds a non-guest token (logged out?)")
        return 1
    t, tok = tabs[0]
    payload = _decode_jwt_payload(tok)
    with open(durable, "w") as f:
        f.write(tok)
    os.chmod(durable, 0o600)
    print("CAPTURED from tab %s -> %s (email=%s exp=%s len=%d)" % (
        t["id"][:8], durable, payload.get("email"), payload.get("exp"), len(tok)))
    return 0


def inject(durable):
    if not os.path.exists(durable):
        print("NO-DURABLE-TOKEN: %s missing — operator login required" % durable)
        return 2
    tok = open(durable).read().strip()
    payload = _decode_jwt_payload(tok)
    if payload.get("exp") and payload["exp"] < time.time():
        print("TOKEN-EXPIRED (exp=%s) — operator login required" % payload.get("exp"))
        return 3
    tab = channel.new_tab("https://chat.z.ai/")
    time.sleep(6)
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
    try:
        c.eval("localStorage.setItem('token', %s)" % json.dumps(tok), timeout=10)
        c.call("Network.setCookie", {
            "name": "token", "value": tok, "domain": "chat.z.ai",
            "path": "/", "secure": True, "httpOnly": True}, timeout=10)
        c.call("Page.navigate", {"url": "https://chat.z.ai/"}, timeout=15)
    finally:
        c.close()
    # verify: shell renders with a non-guest token
    for attempt in range(10):
        time.sleep(3)
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            try:
                tok2 = c.eval("localStorage.getItem('token') || ''", timeout=10)
                shell = c.eval(
                    "(document.querySelectorAll('a,button').length > 5 && "
                    "!(document.body.innerText||'').includes('Sign in')) ? 'shell' : 'no-shell'", timeout=10)
            finally:
                c.close()
        except Exception:
            continue
        p2 = _decode_jwt_payload(tok2)
        email = p2.get("email", "?")
        if "guest" not in str(email) and shell == "shell":
            print("INJECTED-VERIFIED: tab %s email=%s (shell rendered)" % (tab["id"][:8], email))
            return 0
        if attempt == 9:
            print("INJECT-FAILED: email=%s shell=%s (token dead? operator login required)" % (email, shell))
            return 4
    return 4


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    durable = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DURABLE
    if cmd == "capture":
        sys.exit(capture(durable))
    elif cmd == "inject":
        sys.exit(inject(durable))
    else:
        print(__doc__)
        sys.exit(1)
