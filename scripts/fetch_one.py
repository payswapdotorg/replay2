#!/usr/bin/env python3
"""fetch_one.py <chat-id> <workspace-id> <filepath> <dest> — single file via the
workspaces content API with retries (extension-VPN fetch drops are transient)."""
import base64, json, sys, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP

chat, ws, fp, dest = sys.argv[1:5]
js = """(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: %%CHAT%%, workspace_id: %%WS%%, rev: 'latest', filepath: %%FP%%})
  });
  if (!r.ok) return JSON.stringify({error: 'HTTP ' + r.status});
  const buf = await r.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let text = null;
  try { text = new TextDecoder('utf-8', {fatal: true}).decode(bytes); } catch (e) {}
  if (text !== null && !bytes.includes(0)) return JSON.stringify({text: text});
  let bin = '';
  for (let i = 0; i < bytes.length; i += 65536)
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 65536));
  return JSON.stringify({b64: btoa(bin), size: bytes.length});
})()""".replace("%%CHAT%%", json.dumps(chat)).replace("%%WS%%", json.dumps(ws)).replace("%%FP%%", json.dumps(fp))

last = None
for i in range(8):
    try:
        t = channel.find_tab("chat.z.ai")
        if t is None:
            time.sleep(3); continue
        c = CDP(t["webSocketDebuggerUrl"], timeout=30)
        raw = c.eval(js, await_promise=True, timeout=90)
        c.close()
        d = json.loads(raw)
        if "error" in d:
            print(f"attempt {i+1}: {d['error']}"); last = d["error"]; time.sleep(4); continue
        if "text" in d:
            open(dest, "w", newline="").write(d["text"])
        else:
            open(dest, "wb").write(base64.b64decode(d["b64"]))
        import os
        print(f"OK {fp} -> {dest} ({os.path.getsize(dest)} bytes)")
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as e:
        last = str(e)[:100]; time.sleep(4)
print(f"FAILED {fp}: {last}")
raise SystemExit(1)
