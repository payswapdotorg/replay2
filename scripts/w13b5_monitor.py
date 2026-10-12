#!/usr/bin/env python3
"""w13b5 patience monitor — pure-HTTP poller for the platform-crunch window.

Polls every 120s: the chat record (500->OK transition = unwedged), the
workspace count (0->1 = task spawned), and the chat's message count (turn
spawn). Writes one line per observation to /tmp/w13b5_monitor.log. Exits
when the turn spawns (msgs >= 2) or the record goes 404 (destroyed).
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/my-project/replay2/scripts")
import chats_http as ch

CID = "7adb5f6f-d1b9-40f2-896c-924cba27d416"
LOG = "/tmp/w13b5_monitor.log"
TOK = ch.get_token().strip('"')


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def get(path):
    req = urllib.request.Request(
        f"https://chat.z.ai{path}",
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    log("monitor start")
    while True:
        try:
            data = get(f"/api/v1/chats/{CID}")
            rec = data.get("data", data) if isinstance(data, dict) else {}
            inner = rec.get("chat", {}) or {}
            msgs = inner.get("history", {}).get("messages", {})
            if isinstance(msgs, dict):
                msgs = list(msgs.values())
            n = len(msgs)
            gen = any(m.get("generating") for m in msgs if isinstance(m, dict))
            log(f"record OK | msgs={n} gen={gen} title={str(rec.get('title'))[:40]}")
            if n >= 2:
                log("TURN SPAWNED — exiting")
                return 0
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log("record 404 — DESTROYED, exiting")
                return 1
            log(f"record http-{e.code}")
        except Exception as e:
            log(f"record exc {type(e).__name__}")
        try:
            wsd = get("/api/v1/web-dev/workspaces/user-fc")
            total = wsd.get("total", 0)
            mine = [w for w in wsd.get("workspaces", []) if CID in str(w.get("chat_id", ""))]
            log(f"workspaces total={total} mine={len(mine)}")
        except Exception as e:
            log(f"workspaces exc {type(e).__name__}")
        time.sleep(120)


if __name__ == "__main__":
    raise SystemExit(main())
