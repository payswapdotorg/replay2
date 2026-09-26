#!/usr/bin/env python3
"""r30b_bundle_stream.py — the quota-aware streaming bundle harvest.

Two roles, both resilient:
  inject  — the in-page downloader: streams the bundle in 256KB parts to
            localStorage, RETRYING on quota (waiting for the drainer to
            free space). Runs as long as its tab lives.
  drain   — the harvester loop (this process, foreground): every few
            seconds, from ANY healthy tab, read the newest parts, append
            them to the local file, DELETE them from localStorage (freeing
            quota). Reconnects through tab churn automatically.

Usage:
  r30b_bundle_stream.py inject          (one-shot, any healthy tab)
  r30b_bundle_stream.py drain <out>     (foreground loop; Ctrl-C when done)
"""
import base64
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHAT = "dd5c60bf-32f7-4cab-9db1-206bfbaf8906"

JS_INJECT = """
(() => {
  if (window.__streamDL) return 'ALREADY';
  window.__streamDL = true;
  localStorage.setItem('__bs_state', 'running');
  localStorage.setItem('__bs_next', '0');   // next part index to write
  (async () => {
    const setRetry = (k, v) => new Promise((res) => {
      const trySet = () => {
        try { localStorage.setItem(k, v); res(true); }
        catch (e) { setTimeout(trySet, 500); }   // quota: wait for the drainer
      };
      trySet();
    });
    try {
      const tok = localStorage.getItem('token');
      const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
        method: 'POST',
        headers: {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'},
        body: JSON.stringify({chatId: 'dd5c60bf-32f7-4cab-9db1-206bfbaf8906', rev: 'latest',
                              filepath: 'webflix-r30-b.bundle',
                              workspace_id: 'ws-02eff450-d93b-4e60-b467-a9e208d0cdf6'})
      });
      if (!r.ok) { localStorage.setItem('__bs_state', 'err http ' + r.status); return; }
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
        while (carry.length >= 262144) {
          const chunk = carry.subarray(0, 262144);
          carry = carry.subarray(262144);
          await setRetry('__bs_p' + n, toB64(chunk));
          n++;
          localStorage.setItem('__bs_next', String(n));
        }
      }
      if (carry.length) {
        await setRetry('__bs_p' + n, toB64(carry));
        n++;
      }
      localStorage.setItem('__bs_next', String(n));
      localStorage.setItem('__bs_state', 'done:' + n);
    } catch (e) {
      localStorage.setItem('__bs_state', 'err ' + String(e).slice(0, 150));
    } finally {
      window.__streamDL = false;
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
    # open a fresh one
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


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "inject"
    if cmd == "inject":
        c = get_conn()
        if not c:
            print("no healthy tab")
            return 1
        try:
            print(c.eval(JS_INJECT, timeout=15))
            return 0
        finally:
            c.close()
    if cmd == "drain":
        out = sys.argv[2]
        import os
        f = open(out, "ab" if os.path.exists(out) else "wb")
        drained = 0
        c = None
        print("drainer loop started (parts append to file as they land)")
        while True:
            try:
                if c is None:
                    c = get_conn()
                    if c is None:
                        print("  (no healthy tab — retrying)")
                        time.sleep(5)
                        continue
                state = c.eval("localStorage.getItem('__bs_state')", timeout=10)
                nxt = int(c.eval("Number(localStorage.getItem('__bs_next')||0)",
                                 timeout=10) or 0)
                # drain every part present (index 0..nxt-1)
                for i in range(nxt):
                    key = f"__bs_p{i}"
                    if not c.eval(f"localStorage.getItem({key!r}) !== null",
                                  timeout=10):
                        continue  # already drained
                    b64 = c.eval(f"localStorage.getItem({key!r})", timeout=30)
                    if b64 is None:
                        continue
                    f.write(base64.b64decode(b64))
                    drained += 1
                    c.eval(f"localStorage.removeItem({key!r})", timeout=10)
                    print(f"  drained part {i + 1} (total {drained})", flush=True)
                if state and state.startswith("done:"):
                    print(f"COMPLETE: state={state}, drained {drained} parts")
                    f.close()
                    return 0
                if state and state.startswith("err"):
                    print(f"DOWNLOADER ERROR: {state} (drained {drained} so far)")
                    f.close()
                    return 2
                time.sleep(4)
            except Exception as e:
                print(f"  (connection flap: {type(e).__name__} — reconnecting)")
                try:
                    c.close()
                except Exception:
                    pass
                c = None
                time.sleep(3)
    print("unknown cmd")
    return 1


if __name__ == "__main__":
    sys.exit(main())
