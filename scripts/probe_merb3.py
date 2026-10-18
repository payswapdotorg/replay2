#!/usr/bin/env python3
"""Pull mer-B's recent tool-results to reconstruct the delivery state."""
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

files = [
    "tool-results/bash_1792344049931_9916f36a056b.txt",
    "tool-results/read_1792344045181_e216ef74ac50.txt",
    "tool-results/read_1792344043520_e216ef74ac50.txt",
]
for fp in files:
    r = api_post("/api/v1/web-dev/workspaces/files/content",
                 {"chatId": CID, "workspace_id": WID, "rev": "latest", "filepath": fp})
    print(f"\n===== {fp} ({len(r or '')} chars) =====")
    print((r or "")[:1500])
