#!/usr/bin/env python3
"""env_probe.py — passive environment probe for the reset sandbox.

Every 60s, one line to /tmp/env_probe.log:
  bip    browser egress IP (in-page fetch — sees VPN routing; "?" on error)
  login  chat.z.ai auth state (in-page DOM/API check: "in"/"out"/"?")
  chats  server-side chats API liveness for the logged-in account
Never sends anything into any chat. Watcher-friendly single-line format.
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

LOG = "/tmp/env_probe.log"


def bip(tab):
    js = """
    (async () => {
      try { const r = await fetch("https://api.ipify.org", {cache: "no-store"});
            return (await r.text()).trim(); }
      catch (e) { return "?"; }
    })()
    """
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            v = str(c.eval(js, await_promise=True, timeout=20)).strip()
        finally:
            c.close()
        return v if v and len(v) <= 45 and " " not in v else "?"
    except Exception:
        return "?"


def login_state(tab):
    """auth state: /auth URL = mid-login; composer present = in; else out."""
    js = """
    (async () => {
      const onAuth = location.pathname.startsWith('/auth');
      const composer = !!(document.querySelector('#chat-input, textarea'));
      let api = '?';
      try {
        const r = await fetch('/api/v1/chats/', {credentials: 'include'});
        const body = await r.text();
        api = (body.slice(0, 1) === '<') ? 'html' + r.status : 'json' + r.status;
      } catch (e) { api = 'err'; }
      const state = onAuth ? 'auth-page' : (composer ? 'in' : 'out');
      return state + ' api=' + api;
    })()
    """
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            return str(c.eval(js, await_promise=True, timeout=25))
        finally:
            c.close()
    except Exception as e:
        return "wedged:" + str(e)[:40]


def find_chat_tab():
    for t in channel.list_tabs():
        if t.get("type") == "page" and "chat.z.ai" in (t.get("url") or ""):
            return t
    return None


def main():
    open(LOG, "a").write(f"env_probe start pid={__import__('os').getpid()}\n")
    last_bip = None
    while True:
        try:
            tab = find_chat_tab()
            if not tab:
                line = "bip=? no-chat-tab"
            else:
                b = bip(tab)
                marker = "" if b == last_bip else " IP-CHANGE"
                last_bip = b
                line = f"bip={b} login={login_state(tab)}{marker}"
            open(LOG, "a").write(time.strftime("%H:%M:%S ") + line + "\n")
        except Exception as e:
            open(LOG, "a").write(time.strftime("%H:%M:%S ") + f"probe-err {e}\n")
        time.sleep(60)


if __name__ == "__main__":
    main()
