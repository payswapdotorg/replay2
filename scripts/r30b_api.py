#!/usr/bin/env python3
"""r30b_api.py — resilient one-shot workspace API probe (fresh tab each run).

Usage: r30b_api.py <status|ls|lsfull|probe-bundle> [workspace_id]
Opens a FRESH viewer tab (the estate churns), runs the probe, closes it.
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"
WS = "ws-02eff450-d93b-4e60-b467-a9e208d0cdf6"


def fresh_tab():
    t = channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
    time.sleep(9)
    live = {x["id"]: x for x in channel.list_tabs()}
    t2 = live.get(t["id"])
    if not t2:
        raise SystemExit("fresh tab died instantly")
    return t2


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    t = fresh_tab()
    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        tok = (c.eval("localStorage.getItem('token')", timeout=10)
               or "").strip().strip('"')
        hdr = ("{'Authorization': 'Bearer ' + " + json.dumps(tok)
               + ", 'Content-Type': 'application/json'}")
        if cmd == "status":
            js = (f"(async () => {{ const r = await fetch('/api/v1/web-dev/"
                  f"workspaces/status', {{method: 'POST', headers: {hdr}, "
                  f"body: JSON.stringify({{chat_id: {json.dumps(CHAT)}}})}});"
                  f" return JSON.stringify({{s: r.status, b: (await r.text())"
                  f".slice(0, 900)}}); }})()")
        elif cmd == "ls":
            js = (f"(async () => {{ const r = await fetch('/api/v1/web-dev/"
                  f"workspaces/files/ls-tree', {{method: 'POST', headers: {hdr},"
                  f" body: JSON.stringify({{chatId: {json.dumps(CHAT)}, "
                  f"workspace_id: {json.dumps(WS)}}})}});"
                  f" return JSON.stringify({{s: r.status, b: (await r.text())"
                  f".slice(0, 3000)}}); }})()")
        elif cmd == "probe-bundle":
            # size-only probe via a HEAD-ish trick: fetch with Range header
            js = (f"(async () => {{ const r = await fetch('/api/v1/web-dev/"
                  f"workspaces/files/content', {{method: 'POST', headers: "
                  f"Object.assign({hdr}, {{Range: 'bytes=0-1023'}}), "
                  f"body: JSON.stringify({{chatId: {json.dumps(CHAT)}, "
                  f"rev: 'latest', filepath: 'webflix-r30-b.bundle', "
                  f"workspace_id: {json.dumps(WS)}}})}});"
                  f" const buf = await r.arrayBuffer();"
                  f" return JSON.stringify({{s: r.status, len: buf.byteLength, "
                  f"clen: r.headers.get('content-length'), "
                  f"crange: r.headers.get('content-range')}}); }})()")
        else:
            print("unknown cmd")
            return 1
        r = c.eval(js, timeout=90, await_promise=True)
        print(r[:2500])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
