#!/usr/bin/env python3
"""Live view of mer-B's current turn + workspace growth."""
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

# chat body state
tab = channel.find_tab(CID)
if tab:
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const noresp = body.includes('No response');
  return JSON.stringify({len: body.length, stopBtn, noresp, tail: body.slice(-700)});
})()""", timeout=20)
        st = json.loads(raw)
        print(f"CHAT: len={st['len']} stopBtn={st['stopBtn']} noresp={st['noresp']}")
        print("TAIL:", st['tail'][-600:].replace('\n', ' | '))
    finally:
        cdp.close()

# workspace state
tr = json.loads(api_post("/api/v1/web-dev/workspaces/files/ls-tree", {"chatId": CID, "workspace_id": WID}))
if isinstance(tr, dict): tr = tr.get("data", tr)
paths = [str(p) for p in tr] if isinstance(tr, list) else []
print(f"\nTREE: {len(paths)} paths")
blob = "\n".join(paths)
for m in ("COMPLETION-REPORT.md", "MANIFEST.sha256", ".bundle", "packages-merchant", "spec-merchant"):
    c = blob.count(m)
    if c: print(f"  *** {m}: {c} occurrences")
# new files vs the 97 baseline
if len(paths) > 97:
    print("NEW PATHS (first 25):")
    for p in sorted(paths)[-25:]:
        print("  ", p)
