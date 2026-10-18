#!/usr/bin/env python3
"""payswap_lane_watch.py — R3 wave watch v3 (station Task 84, 2026-10-18).

v3 laws (the mer-B false-stall class + the mer-A recycling lesson):
  - LIVENESS = tree-path growth OR worklog.md SIZE growth. Workers that
    live in ~/payswap3-0 grow ONLY worklog.md + tool-results in the
    file-API app root — path-count-only stall detection cries wolf while
    the worker is mid-flight (observed: mer-B at 159/353 tests with
    repeated false stalls).
  - CYCLE 90s + markers checked every cycle: completed sandboxes get
    RECYCLED (mer-A paid this price) — detect markers FAST, harvest FAST.
  - Lane map: mer-B 7b4c016d only (r3-w1 merged c5a4dc7; mer-A recycled).

Observation-only (the §11a law). Never cures, never dispatches.

Launch detached: dfork_launch.py logs/payswap_lane_watch.log <venv-py> payswap_lane_watch.py
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
CYCLE = 90
STALL_AFTER = 1200   # 20 min without ANY growth (tree or worklog) = true stall
WINDOW = 24 * 3600

LANES = {
    "7b4c016d": "r3-w3 merchant-B (test battery in flight)",
    "07f7cac8": "r4-w1 lab (P6-W1 first run; dispatched 16:39Z)",
}
MARKERS = ("COMPLETION-REPORT.md", "MANIFEST.sha256", ".bundle")


def log(msg):
    print(time.strftime("[%m-%d %H:%M:%S] ") + str(msg), flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def page_eval(js, timeout=60):
    import channel
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def api_get(path):
    return page_eval(
        f"(async () => {{ const r = await fetch('{path}', {{credentials:'include'}});"
        f" return await r.text(); }})()")


def api_post(path, body):
    payload = json.dumps(body)
    return page_eval(
        f"(async () => {{ const r = await fetch('{path}', {{method:'POST',"
        f"credentials:'include', headers:{{'Content-Type':'application/json'}},"
        f"body:JSON.stringify({payload})}}); return await r.text(); }})()")


def discover():
    """chat-id -> workspace_id for our lanes, via user-fc (bare-uuid law)."""
    try:
        raw = api_get("/api/v1/web-dev/workspaces/user-fc")
        data = json.loads(raw)
    except Exception:
        return {}
    items = []
    if isinstance(data, dict):
        v = data.get("data", data)
        if isinstance(v, dict):
            for k in ("workspaces", "list", "items"):
                if isinstance(v.get(k), list):
                    items = v[k]
                    break
        elif isinstance(v, list):
            items = v
    out = {}
    for it in items:
        cid = str(it.get("chat_id") or it.get("chatId") or "").removeprefix("chat-")
        wid = it.get("function_name") or it.get("workspace_id") or it.get("id")
        for pfx, lane in LANES.items():
            if cid.startswith(pfx):
                out[pfx] = {"chat": cid, "ws": wid, "lane": lane}
    return out


def tree(lane):
    try:
        raw = api_post("/api/v1/web-dev/workspaces/files/ls-tree",
                       {"chatId": lane["chat"], "workspace_id": lane["ws"]})
        tree_d = json.loads(raw)
        if isinstance(tree_d, dict):
            tree_d = tree_d.get("data", tree_d)
        if isinstance(tree_d, list):
            paths = [str(p) for p in tree_d]
        elif isinstance(tree_d, dict) and isinstance(tree_d.get("files"), list):
            paths = [str(p) for p in tree_d["files"]]
        else:
            paths = []
        return paths
    except Exception as e:
        log(f"tree({lane['lane']}): error {str(e)[:100]}")
        return None


def worklog_size(lane):
    """Byte-length of the app-root worklog.md — the true liveness signal
    for workers whose real trees live outside the file-API index."""
    try:
        raw = api_post("/api/v1/web-dev/workspaces/files/content",
                       {"chatId": lane["chat"], "workspace_id": lane["ws"],
                        "rev": "latest", "filepath": "worklog.md"})
        if raw is None:
            return 0
        return len(raw)
    except Exception:
        return 0


def main():
    os.makedirs(FLAGS, exist_ok=True)
    log("armed v3 — mer-B 7b4c016d only. Liveness = tree OR worklog-size "
        "growth; 90s cycles; stall 1200s; harvest-on-markers FAST (recycling "
        "lesson).")
    outbox("R3 lane watch v3: mer-B only (r3-w1 merged c5a4dc7 + pushed; "
           "mer-A recycled). Liveness now includes worklog.md size growth — "
           "the false-stall class is fixed. Harvest the moment markers "
           "appear: completion idle RECYCLES sandboxes.")
    state = {}
    deadline = time.time() + WINDOW
    while time.time() < deadline:
        try:
            lanes = discover()
        except Exception as e:
            log(f"discover error: {str(e)[:100]}")
            lanes = {}
        for pfx, lane in lanes.items():
            paths = tree(lane)
            if paths is None:
                continue
            wl = worklog_size(lane)
            s = state.setdefault(pfx, {"size": 0, "wl": 0, "last_growth": time.time(),
                                       "stall_flagged": False,
                                       "done_flagged": False, "markers": []})
            grew = False
            if len(paths) != s["size"]:
                if s["size"] > 0:
                    log(f"{lane['lane']}: tree {s['size']} -> {len(paths)}")
                s["size"] = len(paths)
                grew = True
            if wl != s["wl"]:
                if s["wl"] > 0:
                    log(f"{lane['lane']}: worklog {s['wl']} -> {wl} bytes")
                s["wl"] = wl
                grew = True
            if grew:
                s["last_growth"] = time.time()
                s["stall_flagged"] = False
            blob = "\n".join(paths)
            marks = [m for m in MARKERS if m in blob]
            if marks and not s["done_flagged"]:
                s["done_flagged"] = True
                s["markers"] = marks
                log(f"{lane['lane']}: COMPLETION MARKERS {marks}")
                outbox(f"R3 LANE COMPLETE SIGNAL: {lane['lane']} ({lane['chat']}) "
                       f"carries {marks}. TL: harvest_robust.py {lane['chat']} "
                       f"{lane['ws']} NOW (recycling clock is running) → review "
                       f"→ merge.")
            if (not s["stall_flagged"] and not marks
                    and time.time() - s["last_growth"] > STALL_AFTER
                    and s["size"] > 0):
                s["stall_flagged"] = True
                log(f"{lane['lane']}: STALL — no tree/worklog growth in {STALL_AFTER}s")
                outbox(f"R3 LANE TRUE STALL: {lane['lane']} no tree/worklog growth "
                       f"in {STALL_AFTER}s (worklog size {wl}b). TL: check the tab; "
                       f"nudge or accept-loss.")
        time.sleep(CYCLE)
    log("24h window expired — standing down.")


if __name__ == "__main__":
    main()
