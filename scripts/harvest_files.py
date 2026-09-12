#!/usr/bin/env python3
"""harvest_files.py <chat-uuid> <workspace-id> <file> [<file>...] — fetch
specific files from a worker pod via the in-page workspaces files API
(chatId = RAW uuid WITHOUT the chat- prefix; binary comes back as base64).
Writes them under /home/z/leads-harvest/<chat8>/ locally."""
import base64
import json
import os
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

OUTROOT = "/home/z/leads-harvest"

FETCH_JS = """(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: __CHAT__, workspace_id: __WS__, rev: 'latest', filepath: __FP__})
  });
  if (!r.ok) return JSON.stringify({error: (await r.text()).slice(0, 300)});
  const buf = await r.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let text = null;
  try { text = new TextDecoder('utf-8', {fatal: true}).decode(bytes); } catch (e) {}
  if (text !== null && !bytes.includes(0)) return JSON.stringify({text: text});
  let bin = '';
  const CH = 65536;
  for (let i = 0; i < bytes.length; i += CH) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return JSON.stringify({b64: btoa(bin), size: bytes.length});
})()"""


def main():
    chat, wsid = sys.argv[1], sys.argv[2]
    files = sys.argv[3:]
    if not files:
        raise SystemExit("no files requested")
    outdir = os.path.join(OUTROOT, chat[:8])
    os.makedirs(outdir, exist_ok=True)
    tab = channel.find_tab("chat.z.ai")
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=90)
    try:
        for fp in files:
            js = (FETCH_JS.replace("__CHAT__", json.dumps(chat))
                        .replace("__WS__", json.dumps(wsid))
                        .replace("__FP__", json.dumps(fp)))
            try:
                raw = cdp.eval(js, await_promise=True, timeout=90)
                d = json.loads(raw)
            except Exception as e:
                print(f"FAIL {fp}: {type(e).__name__} {e}")
                continue
            if "error" in d:
                print(f"ERROR {fp}: {d['error'][:200]}")
                continue
            local = os.path.join(outdir, os.path.basename(fp))
            if "text" in d:
                open(local, "w", encoding="utf-8").write(d["text"])
                print(f"OK {fp} -> {local} ({len(d['text'])} chars text)")
            else:
                data = base64.b64decode(d["b64"])
                open(local, "wb").write(data)
                print(f"OK {fp} -> {local} ({len(data)} bytes binary)")
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
