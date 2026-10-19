#!/usr/bin/env python3
"""harvest_robust.py — retry-robust, resumable workspace harvest.

The extension-VPN proxy intermittently drops fetch() calls ("Failed to
fetch"); the original harvest_delivery.py dies on the first drop. This
variant retries each file with backoff (drops are transient) and writes
a manifest.

2026-10-19 refresh law (r3-w3d live catch): the OLD skip rule (exists +
size>0) never re-fetched CHANGED files — the local bundle/MANIFEST sat
at commit-1 while the remote had moved to commit-2. Now:
  * If the remote root carries MANIFEST.sha256, it DRIVES the refresh:
    a file is skipped only when its local sha256 matches the manifest.
  * Volatile files (MANIFEST.sha256, *.bundle, *.bundle.b64,
    COMPLETION-REPORT.md, worklog.md) are always re-fetched.
  * Files in the tree but absent from the manifest (new since last
    mirror) are fetched.
  * Optional 5th arg "force" re-fetches everything.

Usage: harvest_robust.py <chat-id> <workspace-id> <remote-prefix> <local-dir> [force]
"""
import base64
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

CHAT = sys.argv[1]
WS = sys.argv[2]
# 2026-10-18 (Task 84): ls-tree paths are ROOT-RELATIVE (no leading slash)
# — an empty prefix must mean "everything", not "/" (which matched 0 files).
# 2026-10-19 (Task 20 merge): "-" is also accepted as the "everything" marker.
_raw_pfx = sys.argv[3]
PREFIX = "" if _raw_pfx in ("", "/", "-") else _raw_pfx.rstrip("/") + "/"
LOCAL = sys.argv[4]
FORCE = len(sys.argv) > 5 and sys.argv[5] == "force"

VOLATILE_NAMES = ("MANIFEST.sha256", "COMPLETION-REPORT.md", "worklog.md")
VOLATILE_SUFFIX = (".bundle", ".bundle.b64")


def is_volatile(fp):
    base = fp.rsplit("/", 1)[-1]
    return (base in VOLATILE_NAMES or base.endswith(VOLATILE_SUFFIX))


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


def eval_retry(cdp, js, tries=6, timeout=90):
    last = None
    for i in range(tries):
        try:
            return cdp.eval(js, await_promise=True, timeout=timeout)
        except Exception as e:
            last = e
            time.sleep(2 + i * 2)   # backoff
    raise last


def fetch_remote(cdp, fp, tries=6, timeout=120):
    js = CONTENT_JS.replace("%%CHAT%%", json.dumps(CHAT)) \
                   .replace("%%WS%%", json.dumps(WS)) \
                   .replace("%%FP%%", json.dumps(fp))
    raw = eval_retry(cdp, js, tries=tries, timeout=timeout)
    d = json.loads(raw)
    if "error" in d:
        raise RuntimeError(str(d["error"]))
    return d


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

        # 2. remote manifest drives the refresh (r3-w3d law)
        rman = {}
        man_path = PREFIX + "MANIFEST.sha256" if PREFIX else "MANIFEST.sha256"
        if man_path in files:
            try:
                d = fetch_remote(cdp, man_path, tries=4, timeout=60)
                text = d.get("text") or base64.b64decode(
                    d["b64"]).decode("utf-8", "replace")
                for line in text.splitlines():
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        rman[parts[1].lstrip("*").strip()] = parts[0].strip()
                print(f"manifest: {len(rman)} entries drive the refresh")
            except Exception as e:
                print(f"manifest fetch failed ({str(e)[:60]}) — existence-skip fallback")

        def local_hash(fp):
            dest = os.path.join(LOCAL, fp[len(PREFIX):])
            if not os.path.exists(dest):
                return None
            h = hashlib.sha256()
            with open(dest, "rb") as f:
                h.update(f.read())
            return h.hexdigest()

        ok = fail = skipped = 0
        failed = []
        for idx, fp in enumerate(files):
            rel = fp[len(PREFIX):]
            dest = os.path.join(LOCAL, rel)
            if not FORCE:
                if is_volatile(fp):
                    pass                    # always re-fetch
                elif fp in rman:
                    if local_hash(fp) == rman[fp]:
                        skipped += 1
                        continue
                elif os.path.exists(dest) and os.path.getsize(dest) > 0:
                    skipped += 1           # no manifest coverage: legacy skip
                    continue
            try:
                d = fetch_remote(cdp, fp)
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
        print(f"done: fetched={ok} skipped={skipped} failed={fail}"
              + (" FORCE" if FORCE else ""))
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
