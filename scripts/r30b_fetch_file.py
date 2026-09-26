#!/usr/bin/env python3
"""r30b_fetch_file.py — fetch a file from the worker's workspace storage
via the files/content API, chunked base64 through CDP.

Usage: r30b_fetch_file.py <filepath> <out-local-path>
"""
import base64
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"
WS = "ws-02eff450-d93b-4e60-b467-a9e208d0cdf6"
REV = "latest"  # content accepts the rev; 'latest' resolves
SUB = "dd5c60bf"

JS_CHUNK = """
(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: CHAT, rev: REV, filepath: PATH, workspace_id: WS})
  });
  if (!r.ok) return JSON.stringify({err: r.status});
  const buf = await r.arrayBuffer();
  const total = buf.byteLength;
  const slice = buf.slice(OFFSET, OFFSET + CHUNK);
  let bin = '';
  const bytes = new Uint8Array(slice);
  const bs = 32768;
  for (let i = 0; i < bytes.length; i += bs) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + bs));
  }
  return JSON.stringify({total: total, b64: btoa(bin)});
})()
"""


def main():
    path = sys.argv[1]
    out = sys.argv[2]
    tabs = [t for t in channel.list_tabs() if SUB in (t.get("url") or "")]
    if not tabs:
        print("NOTAB — open a viewer tab first")
        return 1
    # pick the healthiest tab: probe each with a quick eval
    c = None
    for t in tabs:
        try:
            cand = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            cand.eval("1+1", timeout=8)
            c = cand
            print(f"healthy tab: {t['id'][:10]}")
            break
        except Exception:
            continue
    if c is None:
        print("ALL VIEWER TABS DEAD — open a fresh one")
        return 1
    try:
        tok = (c.eval("localStorage.getItem('token')", timeout=10)
               or "").strip().strip('"')
        js = (JS_CHUNK.replace("TOKEN", json.dumps(tok))
                      .replace("CHAT", json.dumps(CHAT))
                      .replace("REV", json.dumps(REV))
                      .replace("PATH", json.dumps(path))
                      .replace("WS", json.dumps(WS))
                      .replace("OFFSET", "0")
                      .replace("CHUNK", "1048576"))
        r = c.eval(js, timeout=120, await_promise=True)
        d = json.loads(r)
        if "err" in d:
            print(f"ERROR: HTTP {d['err']}")
            return 1
        total = d["total"]
        print(f"file: {path} ({total} bytes)")
        # first chunk is in hand; loop for the rest
        chunks = {0: base64.b64decode(d["b64"])}
        offset = 1048576
        while offset < total:
            js2 = js.replace("OFFSET", "0", 1).replace(
                "OFFSET", str(offset), 1) if False else (
                JS_CHUNK.replace("TOKEN", json.dumps(tok))
                        .replace("CHAT", json.dumps(CHAT))
                        .replace("REV", json.dumps(REV))
                        .replace("PATH", json.dumps(path))
                        .replace("WS", json.dumps(WS))
                        .replace("OFFSET", str(offset))
                        .replace("CHUNK", "1048576"))
            r2 = c.eval(js2, timeout=120, await_promise=True)
            d2 = json.loads(r2)
            if "err" in d2:
                print(f"chunk at {offset} failed: {d2}")
                return 1
            chunks[offset] = base64.b64decode(d2["b64"])
            offset += 1048576
            print(f"  fetched {min(offset, total)}/{total}", flush=True)
        with open(out, "wb") as f:
            for k in sorted(chunks):
                f.write(chunks[k])
        print(f"SAVED: {out} ({sum(len(v) for v in chunks.values())} bytes)")
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
