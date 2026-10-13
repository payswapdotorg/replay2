#!/usr/bin/env python3
"""ppr025_phantom_cleanup.py — one-time backlog cleanup (2026-10-03 18:15Z).

The window hunter's dispatch_worker 'void' only closes the browser TAB;
the empty phantom chat RECORDS accumulated server-side (65+ "New Chat"
0-message records created during the GLM-5.3 rationing destroy-on-create
mode).

This script deletes, on the operator's own account, ONLY records that are:
  - titled exactly "New Chat" (the platform default for a never-landed chat)
  - updated within the last 24h (the phantom-war churn window)
  - verified by a detail probe to contain ZERO messages (user or assistant)

Anything else is left untouched. The hunter v2 now reaps its own phantoms
each cycle, so this backlog pass is one-time.

Run:  python3 ppr025_phantom_cleanup.py [--dry-run]
"""
import json
import sys
import time
import urllib.error
import urllib.request

TOKEN = "/home/z/replay2/scripts/flags/chat_token"
DRY = "--dry-run" in sys.argv
WINDOW = 24 * 3600


def bearer():
    return open(TOKEN).read().strip()


def http(path, method="GET"):
    req = urllib.request.Request("https://chat.z.ai" + path,
                                 headers={"Authorization": "Bearer " + bearer()},
                                 method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read()


def main():
    _, body = http("/api/v1/chats/list")
    items = json.loads(body)
    if isinstance(items, dict):
        items = items.get("chats", [])
    now = time.time()
    cands = [c for c in items
             if (c.get("title") or "") == "New Chat"
             and now - (c.get("updated_at") or 0) < WINDOW]
    print(f"candidates (New Chat, <24h): {len(cands)}")
    deleted = kept = 0
    for c in cands:
        cid = c.get("id") or ""
        if not cid:
            continue
        try:
            _, db = http("/api/v1/chats/" + cid)
            det = json.loads(db)
        except urllib.error.HTTPError as e:
            print(f"  {cid[:8]}: detail HTTP {e.code} — skip (reaper owns it)")
            continue
        except Exception as e:
            print(f"  {cid[:8]}: detail error {e!r} — skip")
            continue
        msgs = det.get("messages") or []
        if msgs:
            print(f"  {cid[:8]}: HAS {len(msgs)} message(s) — KEPT")
            kept += 1
            continue
        if DRY:
            print(f"  {cid[:8]}: 0 messages — would DELETE (dry-run)")
            deleted += 1
            continue
        try:
            st, _ = http("/api/v1/chats/" + cid, method="DELETE")
            print(f"  {cid[:8]}: 0 messages — DELETED ({st})")
            deleted += 1
        except Exception as e:
            print(f"  {cid[:8]}: delete error {e!r} — skip")
        time.sleep(0.4)
    print(f"done: deleted={deleted} kept={kept} dry-run={DRY}")


if __name__ == "__main__":
    main()
