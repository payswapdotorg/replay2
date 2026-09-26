#!/usr/bin/env python3
"""r30b_harvest.py — the workspace-API harvest for the R30-B worker.

Driven from a logged-in chat.z.ai tab (in-page fetch, Bearer from
localStorage). Steps: discover the workspace for the worker chat, check pod
status, then (subcommands): ls-tree, log, archive.
"""
import base64
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

SUB = "dd5c60bf"
CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"

JS_FETCH = """
(async () => {
  const tok = localStorage.getItem('token');
  const r = await fetch(__URL__, __OPTS__);
  const txt = await r.text();
  return JSON.stringify({status: r.status, body: txt.slice(0, __CAP__)});
})()
"""


def run_js(c, url, method="GET", body=None, cap=4000):
    opts = {"method": method, "headers": {}}
    tok = tok_header(c)
    if tok:
        opts["headers"]["Authorization"] = f"Bearer {tok}"
    if body is not None:
        opts["headers"]["Content-Type"] = "application/json"
        opts["body"] = json.dumps(body)
    js = (JS_FETCH.replace("__URL__", json.dumps(url))
                 .replace("__OPTS__", json.dumps(opts))
                 .replace("__CAP__", str(cap)))
    # the async IIFE returns a promise -> awaitPromise
    return c.eval(js, timeout=45, await_promise=True)


def tok_header(c):
    tok = c.eval("localStorage.getItem('token')", timeout=10)
    return (tok or "").strip().strip('"')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    tabs = [t for t in channel.list_tabs() if SUB in (t.get("url") or "")]
    if not tabs:
        print("NOTAB — open a viewer tab first")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=20)
    try:
        if cmd == "discover":
            r = run_js(c, "/api/v1/web-dev/workspaces/user-fc")
            print(r[:3000])
        elif cmd == "status":
            r = run_js(c, "/api/v1/web-dev/workspaces/status", "POST",
                       {"chat_id": CHAT})
            print(r[:2000])
        elif cmd == "ls":
            ws = sys.argv[2]
            r = run_js(c, "/api/v1/web-dev/workspaces/files/ls-tree", "POST",
                       {"chatId": CHAT, "workspace_id": ws}, cap=200000)
            print(r[:12000])
        elif cmd == "log":
            ws = sys.argv[2]
            r = run_js(c, f"/api/v1/web-dev/workspaces/git/log?chatId={CHAT}&workspace_id={ws}")
            print(r[:4000])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
