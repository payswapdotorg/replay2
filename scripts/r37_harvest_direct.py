#!/usr/bin/env python3
"""r37_harvest_direct.py — direct harvest of the r37 relay (no registry needed).
Chat + workspace IDs are known post-recovery. Pulls the manifest, bundle, and
the full evidence tree into /home/z/webflix-harvest/r37/."""
import json, os, sys, urllib.request

FLAGS = "/home/z/replay2/scripts/flags"
TOK = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
CHAT = "c2a2c46b-684d-44d2-83bf-8994bf4702f9"
WS = "ws-0d1c3523-1751-45c3-ab85-ba3cbb22c496"
API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"
OUT = "/home/z/webflix-harvest/r37"

def api(path, body=None, timeout=150):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}/{path}", data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {TOK}")
    if data: req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def fetch_file(path, dest):
    raw = api("content", {"chatId": CHAT, "workspace_id": WS, "rev": "latest", "filepath": path})
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if b"\x00" not in raw:
        try: open(dest, "w", encoding="utf-8", newline="").write(raw.decode("utf-8"))
        except UnicodeDecodeError: open(dest, "wb").write(raw)
    else: open(dest, "wb").write(raw)
    return len(raw)

def main():
    os.makedirs(OUT, exist_ok=True)
    # full tree first
    tree_raw = api("ls-tree", {"chatId": CHAT, "workspace_id": WS})
    try: tree = json.loads(tree_raw)
    except Exception: tree = []
    paths = [p for p in (tree if isinstance(tree, list) else []) if isinstance(p, str)]
    print(f"workspace files: {len(paths)}")
    open(os.path.join(OUT, "_tree.json"), "w").write(json.dumps(paths, indent=1))
    # manifest
    manifest_paths = []
    try:
        n = fetch_file("RELAY-MANIFEST.txt", os.path.join(OUT, "RELAY-MANIFEST.txt"))
        print(f"RELAY-MANIFEST.txt: {n}B")
        for line in open(os.path.join(OUT, "RELAY-MANIFEST.txt")):
            parts = line.split()
            if len(parts) >= 2:
                p = parts[0] if ("/" in parts[0] or parts[0].endswith(".bundle") or parts[0].endswith(".txt")) else parts[1]
                manifest_paths.append(p.strip())
    except Exception as e:
        print(f"RELAY-MANIFEST.txt FAIL: {str(e)[:80]}")
    # fetch everything (tree is the full truth; manifest paths prioritized)
    todo = list(dict.fromkeys(manifest_paths + paths))
    ok = fail = 0; total = 0
    for p in todo:
        if not p or p == "_tree.json": continue
        dest = os.path.join(OUT, p.replace("/", "__"))
        try:
            n = fetch_file(p, dest)
            ok += 1; total += n
        except Exception as e:
            fail += 1
            print(f"  FAIL {p}: {str(e)[:70]}")
    print(f"HARVEST r37: ok={ok} fail={fail} bytes={total} → {OUT}")

if __name__ == "__main__":
    main()
