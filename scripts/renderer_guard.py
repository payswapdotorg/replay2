#!/usr/bin/env python3
"""renderer_guard.py — the OOM-class renderer-death auto-healer (2026-10-14).

Live finding (PCL-003, 13:34Z): this 3.9Gi/no-swap box OOM-kills the shared
chat renderer under streaming pressure; every same-renderer /c/ tab then
wedges into unreadable busy:WebSocketTimeoutException states that the
queue_watch state machine treats with infinite patience (busy resets the
stuck clock). The manual fix that day: Page.reload via browser-level CDP
Target.attachToTarget — same tab id preserved, fresh renderer spawned, the
server-side conversation intact, zero content loss.

This sidecar automates that fix. Additive by design: it never touches
queue_watch.py or any lane state — it only reloads DEAD tabs (a healthy tab
answers a trivial eval; a dead one never does).

Doctrine:
  - probe truth: Runtime.evaluate('1+1') with a short timeout on each
    REGISTRY-live session tab. Works => healthy, do nothing.
  - failure threshold: FAILS_NEEDED consecutive probe failures (spanning
    >= FAIL_WINDOW seconds) = dead renderer signature. A busy-but-alive
    page always answers a trivial eval (the main thread is only blocked
    for the shared-renderer-dead class; today's diagnosis proved this
    separation: HOME/VPN tabs answered while all dead-renderer /c/ tabs
    never did).
  - the fix: browser-level Target.attachToTarget + Page.reload
    (ignoreCache) — the proven sequence, idempotent for live pages.
  - cooldown: RELOAD_COOLDOWN per tab — never hammer a tab that will not
    recover (a reload failure retries only after the cooldown).
  - crash evidence: on each confirmed death, tail dmesg for the OOM line
    (best-effort, logged for forensics).

Launch detached: dfork_launch.py logs/renderer_guard.log <py> renderer_guard.py
"""
import json
import os
import subprocess
import time
import urllib.request

import websocket

BASE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(BASE, "flags", "session_registry.jsonl")
LOG = os.path.join(BASE, "logs", "renderer_guard.log")
HB = os.path.join(BASE, "flags", "renderer_guard_heartbeat")
PIDFILE = os.path.join(BASE, "flags", "renderer_guard.pid")

POLL = 60                 # s between probe rounds
FAILS_NEEDED = 3          # consecutive failures before the death verdict
FAIL_WINDOW = 150         # s the failures must span (rules out blips)
RELOAD_COOLDOWN = 600     # s per tab between reload attempts
EVAL_TIMEOUT = 8          # s for the trivial probe — healthy pages answer fast


def log(msg):
    line = time.strftime("[%m-%d %H:%M:%S] ") + str(msg)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def heartbeat():
    try:
        with open(HB, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def live_tabs():
    """{tab_id: url} for sessions in the registry that are not done/void."""
    out = {}
    try:
        with open(REG, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return out
    for row in rows:
        if row.get("done") or row.get("void"):
            continue
        tid = str(row.get("tab_id") or "")
        url = str(row.get("url") or "")
        if tid and url:
            out[tid] = url
    return out


def page_targets():
    with urllib.request.urlopen("http://localhost:9222/json", timeout=10) as r:
        tabs = json.loads(r.read().decode())
    return {t["id"]: t for t in tabs if t.get("type") == "page"}


def probe(tab):
    """True iff the tab answers a trivial eval."""
    try:
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"],
                                         timeout=EVAL_TIMEOUT)
        try:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": "1+1",
                                           "returnByValue": True}}))
            r = json.loads(ws.recv())
            return r.get("result", {}).get("result", {}).get("value") == 2
        finally:
            ws.close()
    except Exception:
        return False


def reload_tab(target_id):
    """The proven fix: browser-level attach + Page.reload (same tab id)."""
    with urllib.request.urlopen("http://localhost:9222/json/version",
                                timeout=10) as r:
        ver = json.loads(r.read().decode())
    ws = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=15)
    try:
        ws.send(json.dumps({"id": 1, "method": "Target.attachToTarget",
                            "params": {"targetId": target_id,
                                       "flatten": True}}))
        sess = None
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == 1:
                sess = r.get("result", {}).get("sessionId")
                break
        if not sess:
            return False
        ws.send(json.dumps({"id": 2, "method": "Page.reload",
                            "params": {"ignoreCache": True},
                            "sessionId": sess}))
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                r = json.loads(ws.recv())
            except Exception:
                break
            if r.get("id") == 2:
                return "error" not in r
        return True  # command accepted; result event may lag
    finally:
        ws.close()


def oom_evidence():
    try:
        r = subprocess.run(["dmesg"], capture_output=True, text=True,
                           timeout=10)
        lines = [l for l in (r.stdout or "").splitlines()
                 if "Out of memory" in l or "oom-kill" in l]
        return lines[-1][:220] if lines else "no fresh OOM line"
    except Exception as e:
        return f"dmesg unavailable ({e!r})"


def main():
    try:
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    log("renderer_guard armed (OOM-class renderer-death auto-healer)")
    fails = {}      # tab_id -> [timestamps of consecutive failures]
    cooldown = {}   # tab_id -> last reload attempt ts
    while True:
        heartbeat()
        try:
            tabs = page_targets()
        except Exception as e:
            log(f"CDP /json unavailable ({e!r}) — round skipped")
            time.sleep(POLL)
            continue
        for tid, url in live_tabs().items():
            tab = tabs.get(tid)
            if not tab:
                fails.pop(tid, None)   # tab closed = not our problem
                continue
            if probe(tab):
                fails.pop(tid, None)   # healthy — reset the failure run
                continue
            run = fails.setdefault(tid, [])
            run.append(time.time())
            # keep only failures inside the window
            fails[tid] = [t for t in run if time.time() - t <= FAIL_WINDOW]
            n = len(fails[tid])
            span = (fails[tid][-1] - fails[tid][0]) if n > 1 else 0
            if n >= FAILS_NEEDED and span >= FAIL_WINDOW - POLL:
                name = url.split("/c/")[-1][:8] if "/c/" in url else url[:30]
                if time.time() - cooldown.get(tid, 0) < RELOAD_COOLDOWN:
                    log(f"{name} dead-renderer signature (n={n}) but cooldown "
                        f"active — waiting")
                else:
                    cooldown[tid] = time.time()
                    log(f"{name} DEAD RENDERER (n={n} fails over "
                        f"{int(span)}s) — evidence: {oom_evidence()}")
                    ok = reload_tab(tid)
                    log(f"{name} reload {'ACCEPTED' if ok else 'FAILED'} "
                        "(same tab id; fresh renderer expected)")
                fails.pop(tid, None)   # restart the failure run either way
        time.sleep(POLL)


if __name__ == "__main__":
    main()
