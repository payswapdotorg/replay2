#!/usr/bin/env python3
"""r35_harvest.py — harvest the R35 lanes' relays (bundle + manifest + evidence)
from their workspace storage roots via the workspaces files API.

Usage: r34_harvest.py <name>   (any registry name)
Reads the chat uuid from the session registry, resolves the workspace id,
pulls RELAY-MANIFEST.txt + the bundle + the evidence tree into
/home/z/webflix-harvest/<name>/.
"""
import json
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"
TOK = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
OUT_ROOT = "/home/z/webflix-harvest"

KNOWN_BUNDLES = [
    "webflix-r35-thin.bundle",
    
    
]
LIKELY_PATHS = (
    ["RELAY-MANIFEST.txt"] + KNOWN_BUNDLES +
    [f"evidence/{p}" for p in ("r35", "r35b")]
)


def registry_lookup(name):
    rec = None
    for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("name") == name and d.get("action") not in ("void", "failed", "done"):
            if d.get("url") and "/c/" in d["url"]:
                rec = d
    if not rec:
        raise SystemExit(f"no live registry record for {name}")
    chat = rec["url"].rstrip("/").split("/c/")[-1]
    return chat


def api(path, body=None, method=None, timeout=90):
    url = f"{API}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Authorization", f"Bearer {TOK}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def workspace_for(chat):
    data = json.loads(api("user-fc".replace("user-fc", "../workspaces/user-fc")) if False else b"{}")
    # (placeholder — replaced below)


def ws_list():
    # the workspaces list lives one level up from /files
    url = "https://chat.z.ai/api/v1/web-dev/workspaces/user-fc"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TOK}")
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r).get("workspaces", [])


def fetch_file(chat, ws, path, dest):
    raw = api("content", {"chatId": chat, "workspace_id": ws, "rev": "latest", "filepath": path}, timeout=120)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if b"\x00" not in raw:
        try:
            open(dest, "w", encoding="utf-8", newline="").write(raw.decode("utf-8"))
        except UnicodeDecodeError:
            open(dest, "wb").write(raw)
    else:
        open(dest, "wb").write(raw)
    return len(raw)


def main():
    name = sys.argv[1]
    chat = registry_lookup(name)
    ws = None
    for w in ws_list():
        cid = (w.get("chat_id") or "").replace("chat-", "")
        if cid.startswith(chat[:8]):
            ws = w.get("function_name")
            break
    if not ws:
        raise SystemExit(f"no workspace found for {chat[:8]}")
    out = os.path.join(OUT_ROOT, name)
    os.makedirs(out, exist_ok=True)
    print(f"[{name}] chat={chat[:8]} ws={ws[:16]} → {out}")

    # 1. the manifest first (it lists the true paths)
    manifest_paths = []
    try:
        n = fetch_file(chat, ws, "RELAY-MANIFEST.txt", os.path.join(out, "RELAY-MANIFEST.txt"))
        print(f"  RELAY-MANIFEST.txt: {n}B")
        for line in open(os.path.join(out, "RELAY-MANIFEST.txt")):
            parts = line.split()
            if len(parts) >= 2:
                # probe both sha-first and path-first orders
                p = parts[1] if not parts[1].startswith("evidence") and "/" in parts[0] else parts[0]
                if parts[0].startswith("evidence") or parts[0].endswith(".bundle") or "/" in parts[0]:
                    p = parts[0]
                else:
                    p = parts[1]
                manifest_paths.append(p.strip())
    except Exception as e:
        print(f"  RELAY-MANIFEST.txt: NOT PRESENT ({str(e)[:60]})")

    # 2. the bundle(s)
    ok = fail = 0
    for p in list(dict.fromkeys(manifest_paths + KNOWN_BUNDLES)):
        if not p or p.endswith("RELAY-MANIFEST.txt"):
            continue
        dest = os.path.join(out, p.replace("/", "__"))
        try:
            n = fetch_file(chat, ws, p, dest)
            ok += 1
            print(f"  [{ok}] {p} → {n}B")
        except Exception as e:
            fail += 1
            print(f"  FAIL {p}: {str(e)[:70]}")
    print(f"HARVEST {name}: ok={ok} fail={fail} (manifest paths: {len(manifest_paths)})")


if __name__ == "__main__":
    main()
