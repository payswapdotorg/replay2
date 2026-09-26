#!/usr/bin/env python3
"""r30b_bundle_ls.py — the localStorage-persistent bundle downloader.

Injects an in-page downloader that streams the bundle chunk-by-chunk and
persists each chunk to localStorage (disk-backed, survives CDP/tab churn).
The page's JS keeps running as long as ITS tab lives; progress persists
even across viewer reconnects. Poll with quick evals; read out in slices.

Usage: r30b_bundle_ls.py inject | poll | read <out>
"""
import base64
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"

JS_INJECT = """
(() => {
  if (window.__lsDownloadRunning) return 'ALREADY-RUNNING';
  localStorage.setItem('__bundle_state', 'running');
  window.__lsDownloadRunning = true;
  localStorage.setItem('__bundle_state', 'running');
  localStorage.setItem('__bundle_parts', '');
  localStorage.setItem('__bundle_n', '0');
  (async () => {
    try {
      const tok = localStorage.getItem('token');
      const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
        method: 'POST',
        headers: {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'},
        body: JSON.stringify({chatId: 'dd5c60bf-32f7-4cab-9db1-206bfbaf8906', rev: 'latest',
                              filepath: 'webflix-r30-b.bundle',
                              workspace_id: 'ws-02eff450-d93b-4e60-b467-a9e208d0cdf6'})
      });
      if (!r.ok) { localStorage.setItem('__bundle_state', 'err http ' + r.status); return; }
      const reader = r.body.getReader();
      let carry = new Uint8Array(0);
      let n = 0;
      const merge = (a, b) => {
        const m = new Uint8Array(a.length + b.length);
        m.set(a); m.set(b, a.length);
        return m;
      };
      const toB64 = (bytes) => {
        let bin = '';
        const bs = 32768;
        for (let i = 0; i < bytes.length; i += bs) {
          bin += String.fromCharCode.apply(null, bytes.subarray(i, i + bs));
        }
        return btoa(bin);
      };
      for (;;) {
        const {done, value} = await reader.read();
        if (done) break;
        carry = merge(carry, value);
        while (carry.length >= 262144) {        // 256KB binary chunks
          const chunk = carry.subarray(0, 262144);
          carry = carry.subarray(262144);
          localStorage.setItem('__p' + n, toB64(chunk));
          n++;
          localStorage.setItem('__bundle_n', String(n));
        }
      }
      if (carry.length) {
        localStorage.setItem('__p' + n, toB64(carry));
        n++;
      }
      localStorage.setItem('__bundle_n', String(n));
      localStorage.setItem('__bundle_state', 'done');
    } catch (e) {
      localStorage.setItem('__bundle_state', 'err ' + String(e).slice(0, 120));
    } finally {
      window.__lsDownloadRunning = false;
    }
  })();
  return 'INJECTED';
})()
"""


def get_conn():
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
    c = get_conn()
    if not c:
        print("no healthy tab")
        return 1
    try:
        if cmd == "inject":
            print(c.eval(JS_INJECT, timeout=15))
        elif cmd == "poll":
            r = c.eval("JSON.stringify({state: localStorage.getItem('__bundle_state'),"
                       " n: localStorage.getItem('__bundle_n'),"
                       " lastLen: (localStorage.getItem('__p' +"
                       " (Math.max(0, Number(localStorage.getItem('__bundle_n')||0)-1))) || '').length})",
                       timeout=15)
            print(r)
        elif cmd == "read":
            out = sys.argv[2]
            n = int(c.eval("Number(localStorage.getItem('__bundle_n')||0)", timeout=15))
            state = c.eval("localStorage.getItem('__bundle_state')", timeout=10)
            print(f"state={state} parts={n}")
            if state != "done":
                print("not done yet")
                return 1
            parts = []
            for i in range(n):
                p = c.eval(f"localStorage.getItem('__p{i})", timeout=30)
                parts.append(p)
                print(f"  part {i+1}/{n}", flush=True)
            data = base64.b64decode("".join(parts))
            with open(out, "wb") as f:
                f.write(data)
            print(f"SAVED {out}: {len(data)} bytes")
            # cleanup localStorage
            c.eval("for (let i = 0; i < " + str(n) + "; i++) localStorage.removeItem('__p' + i);"
                   " localStorage.removeItem('__bundle_state');"
                   " localStorage.removeItem('__bundle_n');", timeout=30)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
