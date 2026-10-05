#!/usr/bin/env python3
"""probe_unicom_chats.py — TL probe: full turn detail for the live UNiCOM lanes.
Shows every message (role, generating, length, tail) so the TL can judge
completion reports vs mid-work state without opening tabs."""
import json
import sys

import chats_http

LANES = {
    "unicom-w1-002": "bc83c3c0-c8c4-4bf8-9bf0-194a5837fb75",
    "unicom-w2-002": "d8dcc0cf-a16d-413f-ae88-fda180dba742",
    "unicom-w3-002": "c0a0f1ee-39bc-4276-af51-09287fe434c8",
}

for name, cid in LANES.items():
    try:
        d = chats_http.api(f"/api/v1/chats/{cid}")
    except Exception as e:
        print(f"=== {name}: PROBE FAILED {e!r}")
        continue
    rec = d.get("data", d) if isinstance(d, dict) else {}
    inner = rec.get("chat", {}) or rec
    msgs = (inner.get("history", {}) or {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    msgs.sort(key=lambda m: m.get("createdAt") or 0)
    print(f"=== {name} — {(rec.get('title') or '')[:70]} — updated {rec.get('updated_at')}")
    for m in msgs:
        c = m.get("content")
        clen = len(c) if isinstance(c, str) else 0
        tail = ""
        if isinstance(c, str) and c:
            tail = c[-200:].replace("\n", " ⏎ ")
        print(f"  [{m.get('role')}] gen={m.get('generating')} len={clen}")
        if tail:
            print(f"      …{tail!r}")
    print()
