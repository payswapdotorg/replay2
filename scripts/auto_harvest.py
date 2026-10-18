#!/usr/bin/env python3
"""auto_harvest.py — the mer-A lesson closed (Task 84, 2026-10-18).

Completed sandboxes get RECYCLED on completion-idle; mer-A finished
oracle-exact and its files were LOST because the TL wasn't fast enough.
This sentinel watches the live lanes' workspace trees for the completion
markers and launches harvest_robust IMMEDIATELY (read-only content-API
pull; no browser UI driving). The TL verifies + merges afterwards.

Launch: dfork_launch.py logs/auto_harvest.log <venv-py> auto_harvest.py
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
CYCLE = 60
WINDOW = 13 * 3600

LANES = {
    "7b4c016d": {
        "chat": "7b4c016d-4410-4a43-967d-fa597b14e615",
        "ws": "ws-a2a1bd93-efcc-455f-9a89-5a9b58c42895",
        "label": "r3-w3 merchant-B",
        "dest": "/home/z/lanes/r3-w3-harvest",
        "harvested": False,
    },
    "3c307f43": {
        "chat": "3c307f43-4db2-43b7-9dec-a50fc7ffacf4",
        "ws": None,   # discovered dynamically once the sandbox provisions
        "label": "r4-w1b lab",
        "dest": "/home/z/lanes/r4-w1-harvest",
        "harvested": False,
    },
}
MARKERS = ("COMPLETION-REPORT.md", "MANIFEST.sha256")


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
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def tree_paths(chat, ws_id):
    payload = json.dumps({"chatId": chat, "workspace_id": ws_id})
    raw = page_eval(
        f"(async () => {{ const r = await fetch('/api/v1/web-dev/workspaces/"
        f"files/ls-tree', {{method:'POST', credentials:'include', headers:"
        f"{{'Content-Type':'application/json'}}, body: JSON.stringify({payload})}});"
        f" return await r.text(); }})()")
    d = json.loads(raw)
    if isinstance(d, dict):
        d = d.get("data", d)
    if isinstance(d, list):
        return [str(p) for p in d]
    if isinstance(d, dict) and isinstance(d.get("files"), list):
        return [str(p) for p in d["files"]]
    return []


def discover_ws():
    """Fill in r4-w1b's workspace id once it provisions (bare-uuid law)."""
    try:
        raw = page_eval(
            "(async () => { const r = await fetch('/api/v1/web-dev/workspaces/"
            "user-fc', {credentials:'include'}); return await r.text(); })()")
        d = json.loads(raw)
        v = d.get("data", d)
        items = v if isinstance(v, list) else next(
            (v[k] for k in ("workspaces", "list", "items")
             if isinstance(v.get(k), list)), [])
        for it in items:
            cid = str(it.get("chat_id") or it.get("chatId") or "").removeprefix("chat-")
            wid = it.get("function_name") or it.get("workspace_id") or it.get("id")
            for pfx, lane in LANES.items():
                if cid.startswith(pfx) and not lane["ws"]:
                    lane["ws"] = wid
                    log(f"{lane['label']}: workspace provisioned {wid}")
    except Exception as e:
        log(f"discover error: {str(e)[:80]}")


def main():
    log("auto-harvest sentinel online — lanes: " +
        ", ".join(f"{l['label']}({k[:8]})" for k, l in LANES.items()))
    deadline = time.time() + WINDOW
    while time.time() < deadline:
        discover_ws()
        for pfx, lane in LANES.items():
            if lane["harvested"] or not lane["ws"]:
                continue
            try:
                paths = tree_paths(lane["chat"], lane["ws"])
            except Exception as e:
                log(f"{lane['label']}: tree error {str(e)[:80]}")
                continue
            blob = "\n".join(paths)
            marks = [m for m in MARKERS if m in blob]
            if not marks:
                continue
            # MARKERS PRESENT — harvest NOW (the recycling clock is running)
            log(f"{lane['label']}: MARKERS {marks} — LAUNCHING HARVEST")
            outbox(f"AUTO-HARVEST LAUNCH: {lane['label']} carries {marks} — "
                   f"pulling to {lane['dest']} now (recycling clock).")
            r = subprocess.run(
                [sys.executable, os.path.join(BASE, "harvest_robust.py"),
                 lane["chat"], lane["ws"], "", lane["dest"]],
                capture_output=True, text=True, timeout=1800)
            tail = (r.stdout or "").strip().splitlines()
            verdict = tail[-1] if tail else f"rc={r.returncode}"
            log(f"{lane['label']}: harvest verdict: {verdict}")
            # verify the bundle landed
            bundle = None
            for root, _, files in os.walk(lane["dest"]):
                for f in files:
                    if f.endswith(".bundle"):
                        bundle = os.path.join(root, f)
                        break
            lane["harvested"] = True
            outbox(f"AUTO-HARVEST DONE: {lane['label']} -> {verdict} "
                   f"(bundle: {bundle or 'NOT FOUND'}). TL: MANIFEST verify + "
                   f"station battery + review vs oracle + merge + PUSH (PAT era).")
        if all(l["harvested"] for l in LANES.values()):
            log("all lanes harvested — standing down")
            break
        time.sleep(CYCLE)
    log("auto-harvest window expired")


if __name__ == "__main__":
    main()
