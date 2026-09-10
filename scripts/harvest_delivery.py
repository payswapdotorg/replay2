#!/usr/bin/env python3
"""harvest_delivery.py <chat-id> <workspace-id> <remote-subdir> <local-dir>

Harvest files from a worker sandbox's project root via the in-page
workspaces API. rev = "latest" (any non-empty string works; path scope is
the pod's project dir). Text fetched raw; binary fetched as base64 via
arrayBuffer. Writes files locally, prints a manifest with sizes.
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

CONTENT_JS = """
(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: CHAT, workspace_id: WS, rev: 'latest', filepath: FP})
  });
  if (!r.ok) return JSON.stringify({error: await r.text()});
  const buf = await r.arrayBuffer();
  const bytes = new Uint8Array(buf);
  // detect text: no NUL and valid UTF-8 round-trip
  let text = null;
  try {
    const dec = new TextDecoder('utf-8', {fatal: true});
    text = dec.decode(bytes);
  } catch (e) { text = null; }
  if (text !== null && !bytes.includes(0)) {
    return JSON.stringify({text: text});
  }
  let bin = '';
  const CH = 65536;
  for (let i = 0; i < bytes.length; i += CH) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return JSON.stringify({b64: btoa(bin), size: bytes.length});
})()
""".replace("CHAT", "%%CHAT%%").replace("WS", "%%WS%%").replace("FP", "%%FP%%")


def main():
    chat, wsid, subdir, localdir = sys.argv[1:5]
    tab = channel.find_tab("chat.z.ai")
    c = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        # 1. list tree
        js = f"""
        (async () => {{
          const r = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', {{
            method:'POST', credentials:'include',
            headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({{chatId: {json.dumps(chat)}, workspace_id: {json.dumps(wsid)}}})
          }});
          return await r.text();
        }})()
        """
        tree = json.loads(c.eval(js, await_promise=True, timeout=60))
        prefix = subdir.rstrip("/") + "/"
        files = [f for f in tree if f.startswith(prefix)]
        print(f"tree: {len(tree)} files; matching prefix {prefix!r}: {len(files)}")
        if not files:
            print("NO MATCHING FILES — delivery not present yet")
            return 1
        os.makedirs(localdir, exist_ok=True)
        manifest = []
        for fp in files:
            rel = fp[len(prefix):]
            js = CONTENT_JS.replace("%%CHAT%%", json.dumps(chat)) \
                           .replace("%%WS%%", json.dumps(wsid)) \
                           .replace("%%FP%%", json.dumps(fp))
            raw = c.eval(js, await_promise=True, timeout=120)
            d = json.loads(raw)
            if "error" in d:
                print(f"  FAIL {fp}: {str(d['error'])[:120]}")
                manifest.append({"path": fp, "error": str(d["error"])[:200]})
                continue
            dest = os.path.join(localdir, rel)
            os.makedirs(os.path.dirname(dest) or localdir, exist_ok=True)
            if "text" in d:
                with open(dest, "w", encoding="utf-8", newline="") as f:
                    f.write(d["text"])
                size = len(d["text"].encode("utf-8"))
            else:
                data = base64.b64decode(d["b64"])
                with open(dest, "wb") as f:
                    f.write(data)
                size = len(data)
            manifest.append({"path": fp, "local": dest, "size": size})
            print(f"  ok {fp} -> {dest} ({size}b)")
        with open(os.path.join(localdir, "_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=1)
        ok = [m for m in manifest if "size" in m]
        print(f"HARVESTED {len(ok)}/{len(files)} files -> {localdir}")
        return 0 if len(ok) == len(files) else 2
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
