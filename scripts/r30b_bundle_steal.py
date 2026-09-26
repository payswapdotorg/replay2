#!/usr/bin/env python3
"""r30b_bundle_steal.py — the resilient in-page bundle download.

Injects JS that fetches the bundle via the workspace API IN THE PAGE
(survives CDP disconnects — the page's JS keeps running), base64-stores it
on window.__bundleB64, then this script polls/reconnects and reads the
result in slices.

Usage: r30b_bundle_steal.py inject | poll | read <out-path>
"""
import base64
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"
WS = "ws-02eff450-d93b-4e60-b467-a9e208d0cdf6"
URL = f"https://chat.z.ai/c/{CHAT}"

JS_INJECT = """
(async () => {
  window.__bundleB64 = '';
  window.__bundleDone = false;
  window.__bundleErr = null;
  try {
    const tok = localStorage.getItem('token');
    const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
      method: 'POST',
      headers: {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'},
      body: JSON.stringify({chatId: 'dd5c60bf-32f7-4cab-9db1-206bfbaf8906', rev: 'latest',
                            filepath: 'webflix-r30-b.bundle',
                            workspace_id: 'ws-02eff450-d93b-4e60-b467-a9e208d0cdf6'})
    });
    if (!r.ok) { window.__bundleErr = 'http ' + r.status; window.__bundleDone = true; return; }
    const reader = r.body.getReader();
    let bin = '';
    const dec = new TextDecoder('latin1');
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      bin += dec.decode(value, {stream: true});
    }
    // base64 of the latin1 string (byte-faithful)
    const b64 = btoa(bin);
    window.__bundleB64 = b64;
    window.__bundleDone = true;
  } catch (e) {
    window.__bundleErr = String(e);
    window.__bundleDone = true;
  }
})();
'INJECTED'
"""


def get_conn():
    """Fresh healthy tab connection (or None)."""
    tabs = [t for t in channel.list_tabs() if CHAT[:8] in (t.get("url") or "")]
    for t in tabs:
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            c.eval("1+1", timeout=8)
            return c
        except Exception:
            continue
    return None


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "inject"
    if cmd == "inject":
        c = get_conn()
        if not c:
            print("no healthy tab — open one first")
            return 1
        try:
            r = c.eval(JS_INJECT, timeout=15)
            print("inject:", r)
            return 0
        finally:
            c.close()
    if cmd == "poll":
        c = get_conn()
        if not c:
            print("no healthy tab")
            return 1
        try:
            r = c.eval("JSON.stringify({done: window.__bundleDone, "
                       "err: window.__bundleErr, "
                       "len: (window.__bundleB64||'').length})",
                       timeout=15)
            print(r)
            return 0
        finally:
            c.close()
    if cmd == "read":
        out = sys.argv[2]
        c = get_conn()
        if not c:
            print("no healthy tab")
            return 1
        try:
            total = int(c.eval("(window.__bundleB64||'').length", timeout=15))
            print(f"b64 length: {total} ({total * 3 // 4} bytes)")
            CHUNK = 700000  # b64 chars per read
            parts = []
            off = 0
            while off < total:
                piece = c.eval(
                    f"window.__bundleB64.slice({off}, {off + CHUNK})",
                    timeout=60)
                parts.append(piece)
                off += CHUNK
                print(f"  read {off}/{total}", flush=True)
            data = base64.b64decode("".join(parts))
            with open(out, "wb") as f:
                f.write(data)
            print(f"SAVED {out}: {len(data)} bytes")
            return 0
        finally:
            c.close()
    print("unknown cmd")
    return 1


if __name__ == "__main__":
    sys.exit(main())
