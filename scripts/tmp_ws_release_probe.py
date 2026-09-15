#!/usr/bin/env python3
"""tmp_ws_release_probe.py — probe for a workspace release/deactivate endpoint.

ONLY targets dep-010's chat id (5c355d3c) / workspace (ws-cc1c7e45).
Never touches dep-001 (4e2f61fd) or dep-020 (003f515c).
"""
import sys, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

CHAT = "5c355d3c-1aaa-40f0-826c-27207e0c81c4"
WS = "ws-cc1c7e45-3b2f-4a0f-a02c-0837be99db14"

tab = next((t for t in channel.list_tabs() if 'chat.z.ai' in (t.get('url') or '')), None)
if not tab:
    raise SystemExit('no chat.z.ai tab')
c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=45)

def try_call(method, path, body):
    payload = json.dumps(body)
    js = f"""
    (async () => {{
      const r = await fetch('{path}', {{
        method: '{method}',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: `{payload}`
      }});
      const t = await r.text();
      return r.status + ' | ' + t.slice(0, 180);
    }})()
    """
    try:
        return c.eval(js, await_promise=True, timeout=25)
    except Exception as e:
        return 'ERR ' + str(e)[:80]

# harmless probes first (GET-style / OPTIONS won't mutate)
probes = [
    ("POST", "/api/v1/web-dev/workspaces/release", {"chat_id": CHAT}),
    ("POST", "/api/v1/web-dev/workspaces/deactivate", {"chat_id": CHAT}),
    ("POST", "/api/v1/web-dev/workspaces/stop", {"chat_id": CHAT}),
    ("POST", "/api/v1/web-dev/workspaces/status", {"chat_id": CHAT}),  # known-good control
]
for m, p, b in probes:
    print(f"{m} {p} -> {try_call(m, p, b)}")
c.close()
