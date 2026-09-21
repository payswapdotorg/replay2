#!/usr/bin/env python3
"""harvest_delivery.py — generalized direct-HTTP delivery harvest (v2 lineage).

Fetches a worker's staged delivery/ tree from its chat.z.ai sandbox via the
workspaces files API over plain HTTPS (Bearer token from flags/chat_token)
— no browser/CDP dependency (lesson: the in-page path dies under the
recurring renderer-wedge; the API is user-scoped and equivalent).

2026-09-21 lesson (prod019): ls-tree TRUNCATES at ~99 entries — the staging
loop had copied all 33 files (proven by the work log's own command results)
but ls-tree showed only 23; the content endpoint still serves unlisted
paths. When the tree count looks short vs the DELIVERY.txt manifest, pass
explicit paths via --paths (one delivery/-relative path per line).

Usage:
  harvest_delivery.py <session-name> <chat-id> <workspace-id> [--paths <file>]
Output: harvests/<session-name>-delivery/  (files under delivery/ kept,
DELIVERY.txt and evidence docs included). Idempotent: existing non-empty
files are skipped, so re-runs resume.
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"
TOK = open(os.path.join(BASE, "flags", "chat_token")).read().strip().strip('"')


def call(path, body=None, timeout=60):
    url = f"{API}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {TOK}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main() -> int:
    args = sys.argv[1:]
    paths_file = None
    if "--paths" in args:
        i = args.index("--paths")
        paths_file = args[i + 1]
        del args[i:i + 2]
    if len(args) != 3:
        print(__doc__)
        return 2
    name, chat, wsid = args[0], args[1], args[2]
    out = os.path.join(BASE, "harvests", f"{name}-delivery")
    if paths_file:
        files = [ln.strip() for ln in open(paths_file) if ln.strip()]
        print(f"explicit paths: {len(files)} (ls-tree truncation bypass)", flush=True)
    else:
        tree = json.loads(call("ls-tree", {"chatId": chat, "workspace_id": wsid}).decode())
        files = [f for f in tree if f.startswith("delivery/")]
        print(f"delivery files (ls-tree): {len(files)}", flush=True)
    if not files:
        print("NO DELIVERY FILES — wrong workspace or nothing staged", flush=True)
        return 1
    os.makedirs(out, exist_ok=True)
    ok = fail = 0
    for i, fp in enumerate(files):
        rel = fp[len("delivery/"):]
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            ok += 1
            continue
        for attempt in range(4):
            try:
                raw = call("content", {"chatId": chat, "workspace_id": wsid,
                                       "rev": "latest", "filepath": fp}, timeout=110)
                is_text = b"\x00" not in raw
                if is_text:
                    try:
                        txt = raw.decode("utf-8")
                        open(dest, "w", encoding="utf-8", newline="").write(txt)
                    except UnicodeDecodeError:
                        is_text = False
                if not is_text:
                    open(dest, "wb").write(raw)
                ok += 1
                if (i + 1) % 10 == 0:
                    print(f"[{i+1}/{len(files)}] ... {rel[:55]}", flush=True)
                break
            except Exception as e:
                if attempt == 3:
                    fail += 1
                    print(f"FAIL {rel}: {e}", flush=True)
                else:
                    time.sleep(3)
    print(f"HARVEST DONE ok={ok} fail={fail}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
