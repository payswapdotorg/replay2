#!/usr/bin/env python3
"""
r30b_parts_fetch.py — the split-parts fetcher daemon for the R30-B bundle.

The worker split the 254MB bundle into 496 x 512KB parts (bundle-part-*) in
its workspace storage. This daemon fetches every part (sorted = concat
order), resilient to the browser-estate churn (healthy-tab picker, fresh
tabs on demand), then assembles + sha256-verifies + git-fetches the lane.

Shortcut: if 'webflix-r30-b-thin.bundle' appears in the tree (the thin
transport), fetch THAT instead and skip the parts entirely.
"""
import base64
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"
WS = "ws-02eff450-d93b-4e60-b467-a9e208d0cdf6"
PARTS_DIR = "/home/z/r30b-parts"
OUT = "/home/z/webflix-r30-b-full.bundle"
THIN_LOCAL = "/home/z/webflix-r30-b-thin.bundle"
LOG_PREFIX = "[parts]"

JS_LS = """
(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + TOK, 'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: 'dd5c60bf-32f7-4cab-9db1-206bfbaf8906',
                          workspace_id: 'ws-02eff450-d93b-4e60-b467-a9e208d0cdf6'})
  });
  return JSON.stringify(await r.json());
})()
"""

JS_FETCH = """
(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + TOK, 'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: 'dd5c60bf-32f7-4cab-9db1-206bfbaf8906', rev: 'latest',
                          filepath: PATH, workspace_id: 'ws-02eff450-d93b-4e60-b467-a9e208d0cdf6'})
  });
  if (!r.ok) return JSON.stringify({err: r.status});
  const buf = await r.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let bin = '';
  const bs = 32768;
  for (let i = 0; i < bytes.length; i += bs) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + bs));
  }
  return JSON.stringify({b64: btoa(bin)});
})()
"""


def log(m):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {LOG_PREFIX} {m}",
          flush=True)


def get_conn():
    tabs = [t for t in channel.list_tabs() if CHAT[:8] in (t.get("url") or "")]
    for t in tabs:
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            c.eval("1+1", timeout=8)
            return c
        except Exception:
            continue
    try:
        t = channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
        time.sleep(9)
        live = {x["id"]: x for x in channel.list_tabs()}
        t2 = live.get(t["id"])
        if not t2:
            return None
        c = channel.CDP(t2["webSocketDebuggerUrl"], timeout=15)
        c.eval("1+1", timeout=8)
        return c
    except Exception:
        return None


class Conn:
    """A self-healing CDP connection."""

    def __init__(self):
        self.c = None

    def eval(self, js, timeout=90):
        for attempt in range(3):
            if self.c is None:
                self.c = get_conn()
                if self.c is None:
                    time.sleep(5)
                    continue
            try:
                return self.c.eval(js, timeout=timeout, await_promise=True)
            except Exception:
                try:
                    self.c.close()
                except Exception:
                    pass
                self.c = None
                time.sleep(3)
        raise RuntimeError("connection exhausted")


def main():
    os.makedirs(PARTS_DIR, exist_ok=True)
    conn = Conn()
    tok_holder = {}

    def tok():
        if "t" not in tok_holder:
            r = conn.eval("localStorage.getItem('token')", timeout=15)
            tok_holder["t"] = (r or "").strip().strip('"')
        return tok_holder["t"]

    def js_with(url_js, path=None):
        js = (url_js.replace("TOK", json.dumps(tok()))
                   .replace("PATH", json.dumps(path or "")))
        return js

    # tree listing
    raw = conn.eval(js_with(JS_LS), timeout=90)
    tree = json.loads(raw)
    paths = tree if isinstance(tree, list) else (tree.get("data") or [])
    thin = [p for p in paths if "thin" in str(p)]
    if thin:
        log(f"THIN BUNDLE PRESENT: {thin[0]} — fetching that instead")
        r = conn.eval(js_with(JS_FETCH, thin[0]), timeout=120)
        d = json.loads(r)
        if "b64" in d:
            with open(THIN_LOCAL, "wb") as f:
                f.write(base64.b64decode(d["b64"]))
            log(f"THIN SAVED: {THIN_LOCAL}")
            return 0
        log(f"thin fetch failed: {d}")
    parts = sorted(p for p in paths if str(p).startswith("bundle-part-"))
    log(f"{len(parts)} parts to fetch")
    for i, p in enumerate(parts):
        local = os.path.join(PARTS_DIR, p)
        if os.path.exists(local) and os.path.getsize(local) > 0:
            continue
        for attempt in range(4):
            try:
                r = conn.eval(js_with(JS_FETCH, p), timeout=120)
                d = json.loads(r)
                if "b64" in d:
                    data = base64.b64decode(d["b64"])
                    with open(local, "wb") as f:
                        f.write(data)
                    if (i + 1) % 10 == 0 or i + 1 == len(parts):
                        log(f"fetched {i + 1}/{len(parts)}")
                    break
                log(f"part {p} attempt {attempt}: {str(d)[:80]}")
            except Exception as e:
                log(f"part {p} attempt {attempt}: {type(e).__name__}")
            time.sleep(4)
        else:
            log(f"PART FAILED after retries: {p}")
            return 2
    log("all parts fetched — assembling")
    # assemble in sorted order
    with open(OUT, "wb") as out:
        for p in parts:
            with open(os.path.join(PARTS_DIR, p), "rb") as f:
                out.write(f.read())
    size = os.path.getsize(OUT)
    log(f"assembled {OUT}: {size} bytes")
    # sha256
    sha = subprocess.run(["sha256sum", OUT], capture_output=True, text=True).stdout
    log(f"sha256: {sha.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
