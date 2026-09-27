#!/usr/bin/env python3
"""session_restore.py — reopen a dispatched session's tab after a reset.

Opens a fresh tab at the session URL (the conversation persists server-side),
waits for hydration (domLen gate — a blank page must not read as queued),
snapshots the state, and appends a `tab-reopen` registry row so watchers find
the tab. The LIVENESS VERDICT stays with the TL: a bounce-to-home on a fresh
chat is NOT death (lesson 185 — verify via the recent-chats sidebar before
voiding); a loaded history is life.

Usage: session_restore.py <name> <session-url>
"""
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

SNAP_JS = r"""(() => {
  const els = document.querySelectorAll('.chat-assistant');
  const last = els.length ? els[els.length-1] : null;
  return JSON.stringify({
    url: location.href,
    n: els.length,
    aLen: last ? (last.innerText || '').length : 0,
    aTail: last ? (last.innerText || '').slice(-260) : '',
    domLen: (document.body.innerText || '').length,
    bodyHead: (document.body.innerText || '').slice(0, 180)
  });
})()"""


def main():
    name = sys.argv[1]
    url = sys.argv[2]
    tab = channel.new_tab(url)
    snap = None
    for _ in range(9):
        time.sleep(3)
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            try:
                snap = json.loads(c.eval(SNAP_JS, timeout=15))
            finally:
                c.close()
            if snap and snap.get("domLen", 0) > 5000:
                break
        except Exception:
            continue
    snap = snap or {"url": "", "n": 0, "aLen": 0, "aTail": "", "domLen": 0, "bodyHead": ""}
    row = {"action": "tab-reopen", "name": name, "tab_id": tab["id"], "url": url,
           "ts": int(time.time()), "note": "session_restore after reset"}
    os.makedirs(os.path.dirname(REG), exist_ok=True)
    with open(REG, "a") as f:
        f.write(json.dumps(row) + "\n")
    with open(os.path.join(BASE, "flags", "%s.tabid" % name), "w") as f:
        f.write(tab["id"])
    print(json.dumps({
        "restored": True, "tab": tab["id"][:8], "registry_row": "tab-reopen",
        "bounced": "/c/" not in (snap.get("url") or ""),
        "snapshot": snap}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
