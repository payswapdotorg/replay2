#!/usr/bin/env python3
"""r30b_git_probe.py — probe workspace git endpoints (log/diff/show/patch)."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"
WS = "ws-02eff450-d93b-4e60-b467-a9e208d0cdf6"

ENDPOINTS = [
    ("GET", f"/api/v1/web-dev/workspaces/git/diff?chatId={CHAT}&workspace_id={WS}"),
    ("GET", f"/api/v1/web-dev/workspaces/git/commits?chatId={CHAT}&workspace_id={WS}"),
    ("GET", f"/api/v1/web-dev/workspaces/git/status?chatId={CHAT}&workspace_id={WS}"),
    ("GET", f"/api/v1/web-dev/workspaces/git/branches?chatId={CHAT}&workspace_id={WS}"),
]


def main():
    tabs = [t for t in channel.list_tabs() if CHAT[:8] in (t.get("url") or "")]
    if not tabs:
        t = channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
        time.sleep(10)
        live = {x["id"]: x for x in channel.list_tabs()}
        tabs = [live[t["id"]]] if t["id"] in live else []
    if not tabs:
        print("NO TAB")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=30)
    try:
        tok = (c.eval("localStorage.getItem('token')", timeout=10)
               or "").strip().strip('"')
        js_parts = []
        for method, url in ENDPOINTS:
            js_parts.append(
                f"{{m: '{method}', u: '{url}'}}")
        js = (
            "(async () => {"
            " const tok = " + json.dumps(tok) + ";"
            " const eps = [" + ",".join(js_parts) + "];"
            " const out = [];"
            " for (const e of eps) {"
            "   try {"
            "     const r = await fetch(e.u, {headers: {'Authorization': 'Bearer ' + tok}});"
            "     const t = await r.text();"
            "     out.push({u: e.u.split('?')[0].split('/').pop(), s: r.status,"
            "               head: t.slice(0, 150)});"
            "   } catch (err) { out.push({u: e.u, err: String(err).slice(0, 80)}); }"
            " }"
            " return JSON.stringify(out);"
            "})()")
        r = c.eval(js, timeout=60, await_promise=True)
        print(r[:1500])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
