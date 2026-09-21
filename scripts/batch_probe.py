#!/usr/bin/env python3
"""batch_probe.py — CDP-free batch-store truth prober (lesson-107 lineage).

probe_chat.py runs its fetches inside a browser tab; when that tab is
renderer-wedged (WebSocketTimeout) the probe is blind — but the endpoints
it uses are user-scoped plain HTTPS. This tool replicates the probe's core
over urllib + Bearer token (flags/chat_token):

  1. GET  /api/v1/chats/<id>            -> history message ids
  2. POST /api/v1/chats/<id>/messages/batch {ids} -> full payloads

Then reports per-message: role, payload chars, marker spots, and the
filled-report gate verdict (40-hex sha in the 450-char window after each
marker AND no <placeholder> token — the DOM filled-regex doctrine,
2026-09-20) so a packet-template quote can never masquerade as a report.

Usage: batch_probe.py <chat-id> [marker-substring]
Prints one JSON line. Exit 0 = chat alive, 2 = not found, 3 = API error.
"""
import json
import os
import re
import sys
import urllib.request

BASE = "https://chat.z.ai"
FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
TOKEN_CACHE = os.path.join(FLAGS, "chat_token")

HEX40 = re.compile(r"\b[0-9a-f]{40}\b")
PLACEHOLDER = re.compile(r"<[a-zA-Z][^>]{2,60}>")


def get_token() -> str:
    tok = open(TOKEN_CACHE).read().strip().strip('"')
    if not tok:
        raise RuntimeError("empty flags/chat_token — refresh via chats_http.py")
    return tok


def call(path: str, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {get_token()}")
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cid = sys.argv[1]
    marker = sys.argv[2] if len(sys.argv) > 2 else "COMPLETION REPORT"
    try:
        chat = call(f"/api/v1/chats/{cid}")
    except Exception as e:
        print(json.dumps({"err": str(e)}))
        return 3
    msgs = ((chat.get("chat") or chat).get("history") or {}).get("messages") or {}
    if isinstance(msgs, list):
        msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
    by_ts = sorted(msgs.values(), key=lambda m: m.get("timestamp") or 0)
    ids = [m.get("id") for m in by_ts if m.get("id")]
    out = {
        "alive": True,
        "title": (chat.get("chat") or chat).get("title") or chat.get("title"),
        "updated": (chat.get("chat") or chat).get("updated_at") or chat.get("updated_at"),
        "models": (chat.get("chat") or chat).get("models") or chat.get("models") or [],
        "history_msgs": len(by_ts),
        "batch": {"checked": False, "msgs": 0},
        "messages": [],
        "report": False,
    }
    if not ids:
        print(json.dumps(out))
        return 0
    try:
        batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}, timeout=60)
    except Exception as e:
        out["batch"]["err"] = str(e)
        print(json.dumps(out))
        return 0
    data = (batch.get("data") or batch.get("messages")) or {}
    out["batch"] = {"checked": True, "msgs": len(data)}
    for mid, m in data.items():
        if not m:
            continue
        role = m.get("role") or "assistant"
        whole = json.dumps(m)
        spots = 0
        filled = False
        start = 0
        while True:
            mi = whole.find(marker, start)
            if mi < 0:
                break
            spots += 1
            win = whole[mi:mi + 450]
            if HEX40.search(win) and not PLACEHOLDER.search(win):
                filled = True
            start = mi + 1
        gen = m.get("generating")
        entry = {
            "id": mid[:8],
            "role": role,
            "chars": len(whole),
            "generating": gen,
            "marker_spots": spots,
            "filled_report": filled,
        }
        if "content_blocks" in m and isinstance(m["content_blocks"], list):
            entry["blocks"] = len(m["content_blocks"])
        out["messages"].append(entry)
        if filled and role != "user":
            out["report"] = True
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
