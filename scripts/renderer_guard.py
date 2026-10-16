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
import re
import subprocess
import sys
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

# --- the memory trigger (2026-10-14 second-OOM lesson) ---------------------
# A streaming agents-tab page accumulates DOM/JS heap unboundedly (live
# finding: the pcl-003 renderer reached 2.1Gi on a 3.9Gi/no-swap box and
# the kernel OOM-killed first the renderer, then the console; the next
# biggest victim class is the root platform process = session death). A
# mid-generation tab reload is PROVEN SAFE (the conversation is
# server-side; today's reloads and the s8 cure's tab-reopen both resumed
# the lane with zero loss). So: when the page's JS heap crosses the line —
# or the box's available memory is about to hit the floor — reload the
# live tab to cap the biggest consumer. The cooldown bounds the churn.
HEAP_RELOAD_MB = 900      # JS heap threshold per live tab (tertiary)
DOM_RELOAD_NODES = 80000   # DOM node count — the real RSS driver (live
                           # calibration: 54,663 nodes -> 2.2Gi renderer RSS
                           # with only 417MB JS heap; the streaming page
                           # accumulates DOM, not heap)
AVAIL_FLOOR_MB = 700      # box-wide available floor (primary: fire the
                           # reload with real margin — the kernel OOMs at 0)


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
    """{tab_id: (url, name)} for registry sessions not done/void
    (latest record per tab id wins; the name feeds the tab-reopen record).
    R40-d: closure rows are ACTION-typed ('void'/'failed'/'done') — the old
    boolean-field filter never matched them, so voided sessions stayed
    tracked forever (the guard re-opened their tabs on every memory trigger
    — the monotonic tab-accumulation engine behind the probe blindness)."""
    out = {}
    try:
        with open(REG, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return out
    for row in rows:
        tid = str(row.get("tab_id") or "")
        if row.get("action") in ("void", "failed", "done"):
            if tid:
                out.pop(tid, None)  # closure rows clear the tracking
            continue
        if row.get("done") or row.get("void"):
            continue
        url = str(row.get("url") or "")
        name = str(row.get("name") or "")
        if tid and url:
            out[tid] = (url, name)
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


def heap_mb(tab):
    """(heap_MB, dom_nodes) for the page; (None, None) if unreadable."""
    try:
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"],
                                         timeout=EVAL_TIMEOUT)
        try:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression":
                                    "JSON.stringify({h: performance.memory ? "
                                    "Math.round(performance.memory."
                                    "usedJSHeapSize/1048576) : -1, "
                                    "d: document.getElementsByTagName('*')."
                                    "length})",
                                    "returnByValue": True}}))
            r = json.loads(ws.recv())
            v = r.get("result", {}).get("result", {}).get("value")
            if isinstance(v, str):
                d = json.loads(v)
                return int(d.get("h", -1)), int(d.get("d", -1))
            return None, None
        finally:
            ws.close()
    except Exception:
        return None, None


def avail_mb():
    """Box-wide available memory (MemAvailable) in MB."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def close_target(ws, target_id):
    ws.send(json.dumps({"id": 99, "method": "Target.closeTarget",
                        "params": {"targetId": target_id}}))
    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            r = json.loads(ws.recv())
            if r.get("id") == 99:
                return "error" not in r
        except Exception:
            break
    return True


def reopen_tab(target_id, url, name):
    """The memory-reclaim fix: close + fresh tab (2026-10-14 live lesson:
    Page.reload tears down the page but Chrome NEVER returns renderer RSS
    to the OS — the 2.2Gi renderer stayed 2.2Gi with a 260MB heap inside;
    only closing the tab exits the process and gives the memory back). The
    fresh tab keeps the lane's live view; the registry tab-reopen record
    re-aims queue_watch (proven: it follows registry records each poll).
    Open FIRST, close SECOND — the lane never loses its tab."""
    sys.path.insert(0, BASE)
    import channel
    import dispatch_worker as dw
    tab = channel.new_tab(url)
    if tab is None:
        log(f"{name} reopen: fresh-tab open FAILED — old tab kept")
        return False
    dw._save({"action": "tab-reopen", "name": name, "tab_id": tab["id"],
              "url": url, "ts": int(time.time()),
              "note": "renderer_guard memory reclaim: fresh renderer "
                      "(old renderer RSS only returns to the OS on exit)"})
    time.sleep(3)
    with urllib.request.urlopen("http://localhost:9222/json/version",
                                timeout=10) as r:
        ver = json.loads(r.read().decode())
    ws = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=15)
    try:
        ok = close_target(ws, target_id)
    finally:
        ws.close()
    log(f"{name} reopen: fresh tab {tab['id'][:8]}, old {target_id[:8]} "
        f"closed={ok}")
    return True


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


_phantom_seen = {}   # /c/<uuid> -> first-sighting ts (the second-sighting rule)


def sweep_phantoms(tabs):
    """Close /c/ tabs belonging to NO registry chat (2026-10-14 w3-024
    dispatch finding: capacity-fight sends leave phantom /c/ tabs — the
    chat does not exist server-side, yet the tab holds 100-400MB of
    renderer RSS; five burned ~530MB and drove the box to 131MB avail).
    dispatch_worker's own sweep catches the flow-observed class; THIS
    round-level sweep also catches tabs the SITE opens during send
    attempts (never seen by the flow's URL check). SECOND-SIGHTING RULE:
    a uuid is swept only after >=2*POLL seconds with no registry record —
    a just-landed session writes its registry record within seconds of
    the /c/ navigation, so by the next round it is known and protected;
    a phantom stays unknown and dies. Never touches registry chats, bare
    home tabs (login/session/fight base) or non-chat pages."""
    known = set()
    try:
        with open(REG, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    u = json.loads(line).get("url") or ""
                except ValueError:
                    continue
                m = re.search(r"/c/([0-9a-f-]{36})", u)
                if m:
                    known.add(m.group(1))
    except FileNotFoundError:
        return
    now = time.time()
    for tid, t in list(tabs.items()):
        m = re.search(r"/c/([0-9a-f-]{36})", t.get("url") or "")
        if not m or m.group(1) in known:
            continue
        uuid = m.group(1)
        first = _phantom_seen.setdefault(uuid, now)
        if now - first < 2 * POLL:
            continue   # too young — could be a landing session mid-record
        try:
            urllib.request.urlopen(
                "http://localhost:9222/json/close/" + tid,
                timeout=10).read()
            log(f"phantom sweep: closed /c/{uuid[:8]} tab (no registry "
                "chat, {int(now - first)}s old — capacity-fight garbage)")
            _phantom_seen.pop(uuid, None)
        except Exception:
            pass


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
        try:
            sweep_phantoms(tabs)
        except Exception:
            pass
        for tid, (url, sname) in live_tabs().items():
            tab = tabs.get(tid)
            if not tab:
                fails.pop(tid, None)   # tab closed = not our problem
                continue
            if probe(tab):
                fails.pop(tid, None)   # healthy — reset the failure run
                # --- the memory trigger (healthy but fat) ---------------
                hm, dn = heap_mb(tab)
                am = avail_mb()
                if ((hm is not None and hm >= HEAP_RELOAD_MB) or
                        (dn is not None and dn >= DOM_RELOAD_NODES) or
                        (am is not None and am <= AVAIL_FLOOR_MB)):
                    name = sname or (url.split("/c/")[-1][:8]
                                     if "/c/" in url else url[:30])
                    if time.time() - cooldown.get(tid, 0) < RELOAD_COOLDOWN:
                        log(f"{name} memory trigger (heap={hm}MB dom={dn} "
                            f"avail={am}MB) but cooldown active — waiting")
                    else:
                        cooldown[tid] = time.time()
                        log(f"{name} MEMORY TRIGGER: heap={hm}MB dom={dn} "
                            f"avail={am}MB — close+reopen (fresh renderer; "
                            "conversation is server-side; proven safe "
                            "2026-10-14)")
                        ok = reopen_tab(tid, url, sname)
                        log(f"{name} memory reopen "
                            f"{'DONE' if ok else 'FAILED'}")
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
