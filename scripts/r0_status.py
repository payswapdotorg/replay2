#!/usr/bin/env python3
"""r0_status.py — one-shot R0 resident-watch status probe (Lead tooling).

Server-side truth only (lesson-107 HTTP lineage): prints phase/chars/done/filled
for both live R0 worker sessions, the newest freeze-probe reply state, and the
workspace slot occupancy. Exit code 0 always; parse stdout for transitions.

Usage: r0_status.py
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
from batch_probe import call, get_token, BASE  # noqa: E402

SESSIONS = {
    "post002": "e8776d1a-337d-4da5-bc7a-8f52a7ad36af",
    "post003": "83381538-73e8-4a5e-8bb8-4196faeaf7b8",
}
HEX40 = __import__("re").compile(r"\b[0-9a-f]{40}\b")
PLACEHOLDER = __import__("re").compile(r"<[A-Za-z0-9_ -]{4,40}>")


def state_of(cid):
    try:
        chat = call(f"/api/v1/chats/{cid}")
        c = chat.get("chat") or chat
        msgs = (c.get("history") or {}).get("messages") or {}
        if isinstance(msgs, list):
            msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
        if not msgs:
            return ("empty", 0, False, False, 0)
        ids = [m.get("id") for m in msgs.values() if m.get("id")]
        batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}, timeout=60)
        data = (batch.get("data") or batch.get("messages")) or {}
        best = None
        for m in data.values():
            if not m:
                continue
            if (m.get("role") or "assistant") == "assistant":
                if best is None or len(json.dumps(m)) > len(json.dumps(best)):
                    best = m
        if best is None:
            return ("queued", 0, False, False, len(msgs))
        whole = json.dumps(best)
        chars = len(whole)
        done = best.get("done") is True
        filled = False
        start = 0
        while True:
            mi = whole.find("COMPLETION REPORT", start)
            if mi < 0:
                break
            win = whole[mi:mi + 900]
            if HEX40.search(win) and not PLACEHOLDER.search(win):
                filled = True
            start = mi + 1
        return ("generating" if not done else "done", chars, done, filled, len(msgs))
    except Exception as e:
        return (f"err:{type(e).__name__}:{str(e)[:40]}", 0, False, False, 0)


def main():
    print(f"[{time.strftime('%H:%M:%S')}] R0 status:")
    for name, cid in SESSIONS.items():
        phase, chars, done, filled, n = state_of(cid)
        print(f"  {name}: phase={phase} chars={chars} done={done} filled={filled} msgs={n}")
    # workspace slots
    try:
        req = urllib.request.Request(BASE + "/api/v1/web-dev/workspaces/user-fc")
        req.add_header("Authorization", f"Bearer {get_token()}")
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        ws = d.get("workspaces", [])
        print(f"  slots: {d.get('total')}/{d.get('limit')} " +
              (" ".join(w["chat_id"][5:13] for w in ws) if ws else "(free)"))
    except Exception as e:
        print(f"  slots: err {str(e)[:40]}")
    # newest probe chat reply state
    try:
        data = call("/api/v1/chats/list?limit=3")
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = items.get("items", [])
        top = items[0] if items else {}
        cid = top.get("id") or ""
        title = top.get("title") or "New Chat"
        _, chars, done, _, n = state_of(cid)
        print(f"  probe {cid[:8]} '{title[:24]}' msgs={n} done={done} chars={chars}")
    except Exception as e:
        print(f"  probe: err {str(e)[:40]}")


if __name__ == "__main__":
    main()
