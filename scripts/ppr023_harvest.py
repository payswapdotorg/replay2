#!/usr/bin/env python3
"""ppr023_harvest.py — harvest the PPR-023 (OpenClaw) worker's delivery from its pod.

§7 files API at the LATEST snapshot: the delivery tarball (PPR-023-files.tgz),
its sha256, the worklog tail, and the evidence record. Outputs to
/home/z/tmp/ppr023-harvest/. Run AFTER the report flag fires (the final
message boundary snapshots the complete state).

Usage: ppr023_harvest.py
"""
import base64
import json
import os
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "02f9e953-423c-4f25-a199-cb06b8fe1262"
WS = "ws-55fa48de-28d6-4ff1-b713-835b3f7dee11"
OUT = "/home/z/tmp/ppr023-harvest"

FILES = [
    "/home/z/my-project/PPR-023-files.tgz",
    "/home/z/my-project/PPR-023-sha256.txt",
    "/home/z/my-project/worklog.md",
    "/home/z/my-project/Zeck/deploy/evidence/ppr-023.json",
    "/home/z/my-project/Zeck/compat/openclaw/demo/demo-entry.json",
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
        method: 'POST', credentials:'include',
        headers: {'Content-Type': 'application/json', Authorization:'Bearer '+tok},
        body: JSON.stringify({chatId: '%s', rev: '%s', filepath: '%s', workspace_id: '%s'})});
      if (!r.ok) return 'ERR:' + r.status;
      const buf = await r.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      for (let i = 0; i < bytes.length; i += 8192) bin += String.fromCharCode(...bytes.subarray(i, i + 8192));
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
        manifest = {"rev": rev, "chat": CHAT, "ws": WS, "files": {}}
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
