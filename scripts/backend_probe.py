#!/usr/bin/env python3
"""backend_probe.py — one backend-health probe cycle for the outage watch.

2026-09-18 02:5x rewrite (outage lesson): the original design sent the probe
into the dedicated probe chat 74f2887b — but that session went server-side
zombie during the outage (every send silently never landed; messages stayed
at 1 forever), so the sentinel probed into a black hole for hours and would
NEVER have detected recovery. The server API is the acceptance truth, so the
probe now:

  1. opens a FRESH tab at chat.z.ai home and sends "Reply with exactly: OK"
     (a fresh send provably lands server-side even during the outage);
  2. reads the new session id from the tab URL (/c/<cid>);
  3. verifies the user message LANDED server-side (else tooling failure);
  4. polls that fresh chat for an assistant reply (the health signal);
  5. closes the probe tab.

Also checks the legacy probe chat 74f2887b first — if its zombie ever
clears, that's HEALTHY too.

Exit codes: 0 = HEALTHY (assistant reply present — trigger recovery), 
1 = still down (probe landed, no reply), 2 = tooling failure (retry).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

PROBE_CHAT = "74f2887b-75da-48b2-a7a1-8b9e403a61ff"
FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
TOKEN = os.path.join(FLAGS, "chat_token")


def api(path):
    import urllib.request
    tok = open(TOKEN).read().strip().strip('"')
    req = urllib.request.Request("https://chat.z.ai" + path, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def chat_has_reply(cid):
    """(user_landed, assistant_reply) for a chat id, server-side truth."""
    try:
        d = api(f"/api/v1/chats/{cid}")
    except Exception:
        return (None, None)
    msgs = d.get("chat", {}).get("history", {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    user_landed = any(m.get("role") == "user" and m.get("content") for m in msgs)
    has_reply = any(m.get("role") == "assistant" and m.get("content") for m in msgs)
    return (user_landed, has_reply)


def close_tab(prefix):
    try:
        import urllib.request
        for t in channel.list_tabs():
            if (t.get("id") or "").startswith(prefix):
                urllib.request.urlopen(
                    f"http://127.0.0.1:9222/json/close/{t['id']}", timeout=5)
                return True
    except Exception:
        pass
    return False


def main():
    # 0. legacy probe chat: if its zombie ever cleared, that's healthy
    try:
        _u, r = chat_has_reply(PROBE_CHAT)
        if r:
            print("HEALTHY: legacy probe chat has an assistant reply")
            return 0
    except Exception as e:
        print(f"legacy api check failed: {e!r}")

    # 1. fresh tab + fresh session
    tab = None
    try:
        tab = channel.new_tab("https://chat.z.ai/")
    except Exception as e:
        print(f"fresh tab failed: {e!r}")
        return 2
    tp = tab["id"][:8]
    try:
        time.sleep(6)
        r = channel.send_text("Reply with exactly: OK", tab=channel.find_tab(tp))
        if not r.get("ok"):
            # proof-of-send is unreliable during the outage (the composer
            # keeps the draft visible); do NOT fail here — verify server-side
            print("send proof failed — verifying server-side landing instead")
        # 2. read the new session id (tab navigates home -> /c/<cid>)
        cid = None
        for _ in range(10):
            time.sleep(3)
            t = channel.find_tab(tp)
            url = (t or {}).get("url") or ""
            if "/c/" in url:
                cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
                if len(cid) >= 30:
                    break
        if not cid:
            print("no /c/ session after send — tooling failure")
            return 2
        # 3. verify the user message LANDED (send accepted server-side)
        landed = None
        for _ in range(4):
            landed, reply = chat_has_reply(cid)
            if landed:
                break
            time.sleep(4)
        if not landed:
            print("probe never landed server-side — tooling failure")
            return 2
        # 4. poll for the assistant reply
        deadline = time.time() + 30
        while time.time() < deadline:
            landed, reply = chat_has_reply(cid)
            if reply:
                print(f"HEALTHY: fresh probe {cid[:8]} got an assistant reply")
                return 0
            time.sleep(5)
        print(f"DOWN: probe landed in {cid[:8]} but no assistant reply")
        return 1
    except Exception as e:
        print(f"probe failed: {e!r}")
        return 2
    finally:
        close_tab(tp)


if __name__ == "__main__":
    raise SystemExit(main())
