#!/usr/bin/env python3
"""Quick probe: mer-B chat state + workspace tree/worklog/markers."""
import json, os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel

def page_eval(js, timeout=60):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()

def api_get(path):
    return page_eval(f"(async () => {{ const r = await fetch('{path}', {{credentials:'include'}}); return await r.text(); }})()")

def api_post(path, body):
    payload = json.dumps(body)
    return page_eval(f"(async () => {{ const r = await fetch('{path}', {{method:'POST',credentials:'include', headers:{{'Content-Type':'application/json'}},body:JSON.stringify({payload})}}); return await r.text(); }})()")

# --- chat tab state for mer-B ---
MERB = "7b4c016d-4410-4a43-967d-fa597b14e615"
try:
    tab = channel.find_tab(MERB)
    if tab is None:
        print("MERB CHAT: no tab open")
    else:
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const streaming = ['Thinking', 'Generating', 'typing…'].some(m => body.includes(m));
  const noresp = body.includes('No response');
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const tail = body.slice(-600);
  return JSON.stringify({streaming, noresp, stopBtn, len: body.length, tail});
})()""", timeout=20)
            st = json.loads(raw)
            print(f"MERB CHAT: len={st['len']} streaming={st['streaming']} noresp={st['noresp']} stopBtn={st['stopBtn']}")
            print("TAIL:", st['tail'][-500:].replace('\n', ' | '))
        finally:
            cdp.close()
except Exception as e:
    print("MERB CHAT probe error:", e)

# --- workspace discovery ---
raw = api_get("/api/v1/web-dev/workspaces/user-fc")
data = json.loads(raw)
items = []
if isinstance(data, dict):
    v = data.get("data", data)
    if isinstance(v, dict):
        for k in ("workspaces", "list", "items"):
            if isinstance(v.get(k), list):
                items = v[k]; break
    elif isinstance(v, list):
        items = v
print(f"\nWORKSPACES: {len(items)}")
for it in items:
    cid = str(it.get("chat_id") or it.get("chatId") or "").removeprefix("chat-")
    wid = it.get("function_name") or it.get("workspace_id") or it.get("id")
    print(f"  chat={cid[:12]}.. ws={wid}")

# --- mer-B tree + worklog ---
for it in items:
    cid = str(it.get("chat_id") or it.get("chatId") or "").removeprefix("chat-")
    if not cid.startswith("7b4c016d"):
        continue
    wid = it.get("function_name") or it.get("workspace_id") or it.get("id")
    tr = json.loads(api_post("/api/v1/web-dev/workspaces/files/ls-tree",
                             {"chatId": cid, "workspace_id": wid}))
    if isinstance(tr, dict): tr = tr.get("data", tr)
    paths = [str(p) for p in tr] if isinstance(tr, list) else [str(p) for p in tr.get("files", [])] if isinstance(tr, dict) else []
    print(f"\nMERB WS tree: {len(paths)} paths")
    blob = "\n".join(paths)
    for m in ("COMPLETION-REPORT.md", "MANIFEST.sha256", ".bundle"):
        if m in blob:
            print(f"  *** MARKER PRESENT: {m}")
    wl = api_post("/api/v1/web-dev/workspaces/files/content",
                  {"chatId": cid, "workspace_id": wid, "rev": "latest", "filepath": "worklog.md"})
    print(f"  worklog.md: {len(wl) if wl else 0} bytes")
    if wl:
        print("  worklog TAIL:", wl[-800:].replace('\n', ' | '))
    break
