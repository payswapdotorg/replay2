#!/usr/bin/env python3
"""Probe deeper: mer-B tree paths + test content-API reach beyond app root."""
import json, os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel

def page_eval(js, timeout=90):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()

def api_post(path, body):
    payload = json.dumps(body)
    return page_eval(f"(async () => {{ const r = await fetch('{path}', {{method:'POST',credentials:'include', headers:{{'Content-Type':'application/json'}},body:JSON.stringify({payload})}}); return await r.text(); }})()")

CID = "7b4c016d-4410-4a43-967d-fa597b14e615"
WID = "ws-a2a1bd93-efcc-455f-9a89-5a9b58c42895"

tr = json.loads(api_post("/api/v1/web-dev/workspaces/files/ls-tree", {"chatId": CID, "workspace_id": WID}))
if isinstance(tr, dict): tr = tr.get("data", tr)
paths = [str(p) for p in tr] if isinstance(tr, list) else []
print(f"TREE ({len(paths)}):")
for p in sorted(paths):
    print(" ", p)

# Try reaching beyond app root — the home-dir delivery
print("\nCONTENT-API REACH TESTS:")
for fp in ["../r3-w3.bundle", "r3-w3.bundle", "~/payswap3-0/r3-w3.bundle",
           "/home/user/payswap3-0/r3-w3.bundle", "payswap3-0/r3-w3.bundle"]:
    try:
        r = api_post("/api/v1/web-dev/workspaces/files/content",
                     {"chatId": CID, "workspace_id": WID, "rev": "latest", "filepath": fp})
        s = (r or "")
        print(f"  {fp!r}: status={'ERR' if s.startswith('{') or len(s)<10 else 'DATA'} len={len(s)} head={s[:60]!r}")
    except Exception as e:
        print(f"  {fp!r}: EXC {str(e)[:60]}")
