#!/usr/bin/env python3
"""chats_api_outage_sentinel.py — the platform chats-API outage sentinel.

Context (2026-10-19 ~01:10Z): chat.z.ai's chats API family started
returning 405 at ~18:48Z Oct-18 — the site's OWN SPA calls fail
(/api/v1/chats/new, /api/v1/chats/?page=1, /api/v1/chats/<id> all 405;
auth/config/web-dev routes unaffected; verified via network capture in
logs/recover.log). The PCD-002 lane's old chat (ae659afb) was destroyed
server-side in the outage; the recovery send at 00:35:14Z was a phantom
(POST /api/v1/chats/new -> 405; the registry row was invalidated by the
Lead); the hot capacity_recover poller was disarmed to stop full browser
assaults against a dead route.

This sentinel polls the chats API health CHEAPLY (one page-context GET
every POLL seconds over an existing chat.z.ai home tab — no navigation,
no renderer churn). While the route 405s it waits. The moment the route
answers 200, it:
  1. re-writes flags/capacity_recover.pcd-002.json — the supervisor's
     ensure_capacity_recovery() then launches recover_capacity.py which
     owns the full proven create fight (agents tab, capacity popups,
     send, server verification);
  2. touches flags/outage_cleared.marker so the resident watch sees the
     transition;
  3. posts an outbox note and retires.

Launch: nohup python3 chats_api_outage_sentinel.py >> logs/outage_sentinel.log 2>&1 &
"""
import json
import os
import time
import urllib.request
import websocket

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "outage_sentinel.log")
POLL = 300          # s between health probes (cheap; no browser work)
NAME = "pcd-002"
PROMPT_FILE = os.path.join(BASE, "worker-prompts", "pcd-002-rendered.md")


def log(msg):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def find_home_tab():
    with urllib.request.urlopen("http://localhost:9222/json", timeout=10) as r:
        tabs = json.loads(r.read().decode())
    for t in tabs:
        if t.get("type") == "page" and (t.get("url") or "").startswith("https://chat.z.ai/"):
            return t["id"]
    return None


def probe_health():
    """Returns the HTTP status of the chats list route via page context,
    or None on machinery failure (never treated as recovery)."""
    try:
        tid = find_home_tab()
        if not tid:
            return None
        with urllib.request.urlopen("http://localhost:9222/json/version", timeout=10) as r:
            ver = json.loads(r.read().decode())
        ws = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=30)
        try:
            ws.send(json.dumps({"id": 1, "method": "Target.attachToTarget",
                                "params": {"targetId": tid, "flatten": True}}))
            sess = None
            deadline = time.time() + 15
            while time.time() < deadline:
                r = json.loads(ws.recv())
                if r.get("id") == 1:
                    sess = r.get("result", {}).get("sessionId")
                    break
            if not sess:
                return None
            js = ("(async () => { try { const r = await fetch('/api/v1/chats/?page=1', "
                  "{credentials:'include', cache:'no-store'}); return String(r.status); } "
                  "catch (e) { return 'ERR'; } })()")
            ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate",
                                "params": {"expression": js, "awaitPromise": True,
                                           "returnByValue": True},
                                "sessionId": sess}))
            deadline = time.time() + 30
            while time.time() < deadline:
                r = json.loads(ws.recv())
                if r.get("id") == 2 and "result" in r:
                    v = r.get("result", {}).get("result", {}).get("value")
                    return int(v) if (v or "").isdigit() else None
                if r.get("id") == 2:
                    return None
        finally:
            ws.close()
    except Exception:
        return None


def rearm_machinery():
    # Invalidate any phantom sent:true rows first (the watcher's paced
    # assaults during the outage create DOM-verified sends whose POST
    # /api/v1/chats/new 405'd server-side — no /c/ URL ever lands; those
    # rows wedge the poller's create + server check). A later failed
    # action invalidates every earlier create row (registry semantics).
    try:
        reg = os.path.join(FLAGS, "session_registry.jsonl")
        with open(reg, "a") as f:
            f.write(json.dumps({
                "action": "failed", "name": NAME, "ts": int(time.time()),
                "note": "outage sentinel: phantom send rows invalidated at "
                        "chats-API recovery (sends during the outage 405'd "
                        "on /api/v1/chats/new server-side)"}) + "\n")
    except Exception:
        pass
    flag = {"name": NAME, "prompt_file": PROMPT_FILE, "uuid": "",
            "tab_id": "", "ts": int(time.time())}
    with open(os.path.join(FLAGS, f"capacity_recover.{NAME}.json"), "w") as f:
        json.dump(flag, f)
    open(os.path.join(FLAGS, "outage_cleared.marker"), "w").write(
        f"{time.time()} chats-api recovered\n")
    note = {"ts": int(time.time() * 1000), "from": "agent",
            "text": "[lead] CHATS-API OUTAGE CLEARED (sentinel detected the route answering 200) — "
                    "the capacity-recovery machinery is re-armed for the PCD-002 dispatch; the "
                    "resident watch continues. — Tech Lead"}
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    log("chats-api outage sentinel online (poll 300s; on 200 -> re-arm capacity recovery)")
    while True:
        st = probe_health()
        if st == 200:
            log("chats API HEALTHY (200) — re-arming the recovery machinery")
            rearm_machinery()
            log("re-armed; sentinel retiring")
            return 0
        log(f"chats API still down (status={st}) — waiting")
        time.sleep(POLL)


if __name__ == "__main__":
    raise SystemExit(main())
