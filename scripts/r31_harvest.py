#!/usr/bin/env python3
"""r31_harvest.py — the workspace-API harvest for the R31 worker (gap wave).

Cloned from r30b_harvest.py + r30b_fetch_file.py with the chat/WS
parameterized: CHAT is fixed to the R31 worker chat; WS is passed as an
argument (discovered via `discover` once the worker's workspace exists).

Subcommands:
  discover                     — GET workspaces/user-fc (list all WS)
  status                       — POST workspaces/status {chat_id}
  ls <ws>                      — files/ls-tree for the chat+ws
  log <ws>                     — git log for the chat+ws
  fetch <ws> <filepath> <out>  — chunked file fetch (1MB chunks, CDP)
"""
import base64
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "ca87c5cf-ea75-44ed-a972-70c4bef25f21"
SUB = "ca87c5cf"
REV = "latest"

JS_FETCH = """
(async () => {
  const tok = localStorage.getItem('token');
  const r = await fetch(__URL__, __OPTS__);
  const txt = await r.text();
  return JSON.stringify({status: r.status, body: txt.slice(0, __CAP__)});
})()
"""

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


def pick_tab():
    tabs = [t for t in channel.list_tabs() if SUB in (t.get("url") or "")]
    if not tabs:
        return None
    # healthiest-tab picker (the r30b_fetch_file pattern)
    for t in tabs:
        try:
            cand = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            cand.eval("1+1", timeout=8)
            return cand
        except Exception:
            continue
    return None


def tok_of(c):
    return (c.eval("localStorage.getItem('token')", timeout=10)
            or "").strip().strip('"')


def run_js(c, url, method="GET", body=None, cap=4000):
    opts = {"method": method, "headers": {}}
    tok = tok_of(c)
    if tok:
        opts["headers"]["Authorization"] = f"Bearer {tok}"
    if body is not None:
        opts["headers"]["Content-Type"] = "application/json"
        opts["body"] = json.dumps(body)
    js = (JS_FETCH.replace("__URL__", json.dumps(url))
                 .replace("__OPTS__", json.dumps(opts))
                 .replace("__CAP__", str(cap)))
    return c.eval(js, timeout=45, await_promise=True)


def fetch_file(c, ws, path, out):
    tok = tok_of(c)
    base = (JS_CHUNK.replace("TOKEN", json.dumps(tok))
                    .replace("CHAT", json.dumps(CHAT))
                    .replace("REV", json.dumps(REV))
                    .replace("PATH", json.dumps(path))
                    .replace("WS", json.dumps(ws)))
    js0 = base.replace("OFFSET", "0").replace("CHUNK", "1048576")
    r = c.eval(js0, timeout=120, await_promise=True)
    d = json.loads(r)
    if "err" in d:
        print(f"ERROR: HTTP {d['err']}")
        return 1
    total = d["total"]
    print(f"file: {path} ({total} bytes)")
    chunks = {0: base64.b64decode(d["b64"])}
    offset = 1048576
    while offset < total:
        js = base.replace("OFFSET", str(offset)).replace("CHUNK", "1048576")
        rd = json.loads(c.eval(js, timeout=180, await_promise=True))
        if "err" in rd:
            print(f"ERROR at offset {offset}: HTTP {rd['err']}")
            return 1
        chunks[offset] = base64.b64decode(rd["b64"])
        offset += 1048576
        if offset % (16 * 1048576) < 1048576:
            print(f"  ... {offset}/{total}")
    with open(out, "wb") as f:
        for k in sorted(chunks):
            f.write(chunks[k])
    print(f"saved: {out} ({total} bytes)")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "discover"
    c = pick_tab()
    if c is None:
        print("NOTAB — open a viewer tab on the worker chat first")
        return 1
    try:
        if cmd == "discover":
            r = run_js(c, "/api/v1/web-dev/workspaces/user-fc", cap=20000)
            print(r[:20000])
        elif cmd == "status":
            r = run_js(c, "/api/v1/web-dev/workspaces/status", "POST",
                       {"chat_id": CHAT})
            print(r[:4000])
        elif cmd == "ls":
            ws = sys.argv[2]
            r = run_js(c, "/api/v1/web-dev/workspaces/files/ls-tree", "POST",
                       {"chatId": CHAT, "workspace_id": ws}, cap=400000)
            print(r[:200000])
        elif cmd == "log":
            ws = sys.argv[2]
            r = run_js(c, f"/api/v1/web-dev/workspaces/git/log?chatId={CHAT}&workspace_id={ws}")
            print(r[:8000])
        elif cmd == "fetch":
            ws, path, out = sys.argv[2], sys.argv[3], sys.argv[4]
            return fetch_file(c, ws, path, out)
        else:
            print("usage: r31_harvest.py discover|status|ls|log|fetch")
            return 2
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
