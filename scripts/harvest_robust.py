#!/usr/bin/env python3
"""harvest_robust.py — retry-robust, resumable workspace harvest.

The extension-VPN proxy intermittently drops fetch() calls ("Failed to
fetch"); the original harvest_delivery.py dies on the first drop. This
variant retries each file with backoff (drops are transient), skips files
already harvested with a non-trivial size, and writes a manifest.

Usage: harvest_robust.py <chat-id> <workspace-id> <remote-prefix> <local-dir>
"""
import json
import os
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

CHAT = sys.argv[1]
WS = sys.argv[2]
PREFIX = sys.argv[3].rstrip("/") + "/"
LOCAL = sys.argv[4]

CONTENT_JS = """
(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: CHAT, workspace_id: WS, rev: 'latest', filepath: FP})
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
})()
""".replace("CHAT", "%%CHAT%%").replace("WS", "%%WS%%").replace("FP", "%%FP%%")

import base64


def eval_retry(cdp, js, tries=6, timeout=90):
    last = None
    for i in range(tries):
        try:
            return cdp.eval(js, await_promise=True, timeout=timeout)
        except Exception as e:
            last = e
            time.sleep(2 + i * 2)   # backoff
    raise last


def main():
    tab = channel.find_tab("chat.z.ai")
    cdp = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        # 1. tree (with retries)
        payload = json.dumps({"chatId": CHAT, "workspace_id": WS})
        js = f"""
        (async () => {{
          const r = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', {{
            method:'POST', credentials:'include',
            headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({payload})
          }});
          return await r.text();
        }})()
        """
        tree_raw = eval_retry(cdp, js, tries=8, timeout=60)
        tree = json.loads(tree_raw)
        files = [f for f in tree if isinstance(f, str) and f.startswith(PREFIX)]
        print(f"tree: {len(tree)} files; matching {PREFIX!r}: {len(files)}")
        if not files:
            return 1
        os.makedirs(LOCAL, exist_ok=True)
        ok = fail = skipped = 0
        failed = []
        for idx, fp in enumerate(files):
            rel = fp[len(PREFIX):]
            dest = os.path.join(LOCAL, rel)
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                skipped += 1
                continue
            js = CONTENT_JS.replace("%%CHAT%%", json.dumps(CHAT)) \
                           .replace("%%WS%%", json.dumps(WS)) \
                           .replace("%%FP%%", json.dumps(fp))
            try:
                raw = eval_retry(cdp, js, tries=6, timeout=120)
                d = json.loads(raw)
                if "error" in d:
                    fail += 1
                    failed.append(fp)
                    print(f"  FAIL {fp}: {str(d['error'])[:80]}")
                    continue
                os.makedirs(os.path.dirname(dest) or LOCAL, exist_ok=True)
                if "text" in d:
                    with open(dest, "w", encoding="utf-8", newline="") as f:
                        f.write(d["text"])
                else:
                    with open(dest, "wb") as f:
                        f.write(base64.b64decode(d["b64"]))
                ok += 1
                if (ok % 25) == 0:
                    print(f"  ... {ok} fetched ({idx+1}/{len(files)})")
            except Exception as e:
                fail += 1
                failed.append(fp)
                print(f"  ERR  {fp}: {str(e)[:80]}")
        print(f"done: fetched={ok} skipped(resumed)={skipped} failed={fail}")
        if failed:
            with open(os.path.join(LOCAL, "_failed.json"), "w") as f:
                json.dump(failed, f, indent=1)
            print("failed list -> _failed.json (re-run to resume)")
            return 2
        return 0
    finally:
        cdp.close()


if __name__ == "__main__":
    sys.exit(main())
