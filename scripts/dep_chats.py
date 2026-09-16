#!/usr/bin/env python3
"""dep_chats.py — registry-dynamic chat-id resolution for the DEP sentinels.

The sentinels (dep_watch.py / dep_rescue.py) used to hardcode chat ids per
landing, which forced a manual re-point after every re-landing round. This
module resolves the ids from the session registry instead, using the same
ordering semantics as dispatch_worker._find / recover_capacity:

  - walk rows in order; a later void/failed/done row for a name invalidates
    every earlier create row for that name
  - a create row with sent=True and no action field is a live session
  - the chat uuid is parsed from the row's url (https://chat.z.ai/c/<uuid>)
  - with multiple live creates the newest (last in file order) wins

Falls back to the last hardcoded map when a name has no live registry row,
so the sentinels always have something to poll. Call resolve() again after
any landing to pick up the new chat id automatically.
"""
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

NAMES = ["dep-001", "dep-010", "dep-020", "dep-025", "dep-012"]

# Last manually-pointed ids (pre-registry era / safety net).
FALLBACK = {
    "dep-001": "6999d433-9206-499c-8974-564ea879a7f6",
    "dep-010": "e6375f3c-370c-44f1-ad25-00e2db80eb32",
    "dep-020": "003f515c-c3e7-468b-8665-7e1463d7df2d",
    "dep-025": "340016bf-7dc2-4057-9756-a6cb6351bf3c",
    "dep-012": "8e1ef7e0-b5b3-4083-810f-682c02e860cf",
}

_UUID_RE = re.compile(r"/c/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def _uuid_from(row):
    for key in ("chat_id", "url"):
        v = row.get(key)
        if isinstance(v, str):
            m = _UUID_RE.search(v) or (re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v)
                and v)
            if m:
                return m.group(1) if hasattr(m, "group") else m
    return None


def resolve():
    """Return {name: chat-uuid} — registry-live rows first, FALLBACK otherwise."""
    live = {}
    try:
        with open(REG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                name = r.get("name")
                if name not in NAMES:
                    continue
                action = r.get("action")
                if action in ("void", "failed", "done"):
                    live.pop(name, None)   # invalidates every earlier create
                elif r.get("sent") and action is None:
                    cid = _uuid_from(r)
                    if cid:
                        live[name] = cid   # newest live create wins
    except Exception:
        pass
    out = {}
    for n in NAMES:
        cid = live.get(n) or FALLBACK.get(n)
        if cid:
            out[n] = cid
    return out


if __name__ == "__main__":
    import time
    resolved = resolve()
    print("resolved:", json.dumps(resolved, indent=1))
    print("registry mtime:", time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(REG))))
