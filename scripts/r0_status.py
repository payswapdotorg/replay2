#!/usr/bin/env python3
"""r0_status.py — resident-watch status probe (recovery-watch mode).

No live worker sessions until the platform agent-chat infra recovers
(2026-09-25 outage: fresh dispatches land then get reaped; probe turns
come back empty-done). This probe reports the recovery signals:

  1. sandbox slot occupancy (/api/v1/web-dev/workspaces/user-fc)
  2. the newest chat (id/title/msgs/assistant state) — probe chats appear
     hourly; a SURVIVING probe chat with non-empty assistant content =
     PLATFORM RECOVERED -> Lead re-dispatches POST-002/POST-003.
  3. the freeze-probe watch log tail (hourly DOWN/HEALTHY verdicts)

Usage: r0_status.py
"""
import json
import re
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
from batch_probe import call, get_token, BASE  # noqa: E402

HEX40 = re.compile(r"\b[0-9a-f]{40}\b")
FREEZE_LOG = "/tmp/freeze_probe_watch.log"


def main():
    print(f"[{time.strftime('%H:%M:%S')}] recovery-watch status:")
    # slots
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
    # newest 3 chats
    try:
        data = call("/api/v1/chats/list?limit=3")
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = items.get("items", [])
        items = items[:3]
        for it in items:
            cid = it.get("id") or ""
            title = (it.get("title") or "New Chat")[:30]
            try:
                chat = call(f"/api/v1/chats/{cid}")
                c = chat.get("chat") or chat
                msgs = (c.get("history") or {}).get("messages") or {}
                if isinstance(msgs, list):
                    msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
                ids = [m.get("id") for m in msgs.values() if m.get("id")]
                alen, adone = 0, None
                if ids:
                    batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}, timeout=60)
                    dd = (batch.get("data") or batch.get("messages")) or {}
                    for m in dd.values():
                        if m and m.get("role") == "assistant":
                            alen = len(m.get("content") or "")
                            adone = m.get("done")
                print(f"  chat {cid[:8]} '{title}' msgs={len(msgs)} a_len={alen} a_done={adone}"
                      + ("  <<< RECOVERY SIGNAL (assistant content!)" if alen > 0 else ""))
            except Exception:
                print(f"  chat {cid[:8]} '{title}' (detail 500 = reaped)")
    except Exception as e:
        print(f"  chats: err {str(e)[:40]}")
    # freeze probe verdict
    try:
        lines = open(FREEZE_LOG).read().strip().splitlines()
        print(f"  freeze: {lines[-1][:110] if lines else 'no log'}")
    except Exception:
        print("  freeze: no log")


if __name__ == "__main__":
    main()
