#!/usr/bin/env python3
"""check_workspaces.py — worker sandbox state via in-page workspaces API.

Usage: check_workspaces.py            # list active workspaces + pod status
       check_workspaces.py <chat_id>  # + file tree of that chat's workspace
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def page_eval(js, timeout=60):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def api_get(path):
    js = f"""
    (async () => {{
      const r = await fetch('{path}', {{credentials:'include'}});
      const t = await r.text();
      return t.slice(0, 300000);
    }})()
    """
    return page_eval(js)


def api_post(path, body):
    payload = json.dumps(body)
    js = f"""
    (async () => {{
      const r = await fetch('{path}', {{
        method: 'POST',
        credentials:'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({payload})
      }});
      const t = await r.text();
      return t.slice(0, 300000);
    }})()
    """
    return page_eval(js)


def main():
    raw = api_get("/api/v1/web-dev/workspaces/user-fc")
    print("== user-fc workspaces:")
    try:
        data = json.loads(raw)
        print(json.dumps(data, indent=1)[:2500])
    except Exception:
        print(raw[:2000])
        data = {}
    # pod status per workspace
    items = []
    if isinstance(data, dict):
        v = data.get("data", data)
        if isinstance(v, dict):
            for k in ("workspaces", "list", "items"):
                if isinstance(v.get(k), list):
                    items = v[k]
                    break
        elif isinstance(v, list):
            items = v
    for it in items:
        cid = it.get("chat_id") or it.get("chatId")
        wid = it.get("function_name") or it.get("workspace_id") or it.get("id")
        if not cid:
            continue
        print(f"== status chat={cid[:12]} ws={str(wid)[:16]} active={it.get('is_active')}")
        print(api_post("/api/v1/web-dev/workspaces/status", {"chat_id": str(cid).removeprefix("chat-")})[:1200])
    # optional tree
    if len(sys.argv) > 1:
        cid = sys.argv[1]
        wid = None
        for it in items:
            icid = str(it.get("chat_id") or it.get("chatId") or "").removeprefix("chat-")
            if icid.startswith(cid[:8]):
                wid = it.get("function_name") or it.get("workspace_id") or it.get("id")
                cid = icid
                break
        if wid is None:
            print("no workspace found for chat", cid)
            return
        print(f"== ls-tree chat={cid} ws={wid}:")
        print(api_post("/api/v1/web-dev/workspaces/files/ls-tree",
                       {"chatId": str(cid).removeprefix("chat-"), "workspace_id": wid})[:20000])


if __name__ == "__main__":
    main()
