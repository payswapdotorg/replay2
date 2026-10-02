#!/usr/bin/env python3
"""ppr022_harvest.py — harvest the PPR-022 r4 worker's delivery from its pod.

§7 files API at the LATEST snapshot: the delivery tarball (PPR-022-files.tgz),
its sha256, the worklog tail, and the evidence record. Outputs to
/home/z/tmp/ppr022-harvest/. Run AFTER the report flag fires (the final
message boundary snapshots the complete state).

Usage: ppr022_harvest.py [--chat 6365132a-...] [--ws ws-46ae2371-...]
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

CHAT = "6365132a-40ff-4920-ad79-1a098c57d93d"
WS = "ws-46ae2371-0130-498a-9eed-64522b7b2148"
OUT = "/home/z/tmp/ppr022-harvest"

FILES = [
    "/home/z/my-project/PPR-022-files.tgz",
    "/home/z/my-project/PPR-022-sha256.txt",
    "/home/z/my-project/worklog.md",
    "/home/z/my-project/Zeck/deploy/evidence/ppr-022.json",
    "/home/z/my-project/Zeck/compat/hermes-agent/demo/demo-entry.json",
]


def latest_rev(home_ws):
    js = """(async () => {
      const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
      const r = await fetch('/api/v1/web-dev/workspaces/git/log?chatId=%s&limit=3', {headers:{Authorization:'Bearer '+tok}, credentials:'include'});
      const j = await r.json();
      const c = (j.data||[])[0];
      return c ? c.commit_hash : '';
    })()""" % CHAT
    return home_ws.eval(js, await_promise=True, timeout=60)


def fetch_file(home_ws, rev, path):
    js = """(async () => {
      const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
      const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
        method: 'POST', credentials: 'include',
        headers: {'Content-Type':'application/json', Authorization:'Bearer '+tok},
        body: JSON.stringify({chatId: '%s', rev: '%s', filepath: '%s', workspace_id: '%s'})});
      if (!r.ok) return 'ERR:' + r.status;
      const buf = await r.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode(...bytes.subarray(i, i+8192));
      return btoa(bin);
    })()""" % (CHAT, rev, path, WS)
    raw = home_ws.eval(js, await_promise=True, timeout=180)
    if not raw or raw.startswith("ERR:"):
        return None, raw
    return base64.b64decode(raw), None


def main():
    os.makedirs(OUT, exist_ok=True)
    tabs = channel.list_tabs()
    home = next(t for t in tabs if (t.get("url") or "").rstrip("/") == "https://chat.z.ai")
    ws = channel.CDP(home["webSocketDebuggerUrl"])
    try:
        rev = latest_rev(ws)
        print("latest rev:", rev[:12])
        if not rev:
            return 1
        manifest = {"rev": rev, "chat": CHAT, "files": {}}
        for path in FILES:
            data, err = fetch_file(ws, rev, path)
            name = os.path.basename(path)
            if data is None:
                print(f"  {name}: MISSING ({err})")
                manifest["files"][name] = {"status": "missing", "err": str(err)[:80]}
                continue
            with open(os.path.join(OUT, name), "wb") as f:
                f.write(data)
            print(f"  {name}: {len(data)} bytes")
            manifest["files"][name] = {"status": "ok", "bytes": len(data)}
        with open(os.path.join(OUT, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=1)
        print("harvest complete ->", OUT)
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
