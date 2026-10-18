#!/usr/bin/env python3
"""r4_gate.py — auto-redispatch R4-W1 when the degraded window truly clears.

The window's clear-signal (Task 85 law): a FRESH chat establishing itself —
r3-w3c gets its /c/ url AND shows real generation growth two cycles in a
row. Fresh chats cannot establish in the degraded window (nine reaped so
far); when one does, the window is open and the (patched) dispatch ladder
gets relaunched for R4-W1.

5-min cycles, 14h cap. Launch:
  dfork_launch.py logs/r4_gate.log <venv-py> r4_gate.py
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
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
CYCLE = 300
CAP = 14 * 3600
SEED_LANE = "payswap3-r3-w3c"   # the fresh chat we watch for establishment


def log(msg):
    print(time.strftime("[%m-%d %H:%M:%S] ") + str(msg), flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def seed_record():
    try:
        recs = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except Exception:
        return None
    latest = None
    for r in recs:
        if r.get("name") == SEED_LANE:
            if r.get("action") in ("void", "done", "failed"):
                latest = None
            elif r.get("sent") and r.get("url"):
                latest = r
    return latest


def lane_state(rec):
    """Establishment probe: (has_chat_url, body_len) or None if unprobeable."""
    tabs = channel.list_tabs()
    tab = None
    tid = rec.get("tab_id")
    if tid:
        for t in tabs:
            if t.get("id") == tid:
                tab = t
                break
    url = rec.get("url") or ""
    if tab is None and "/c/" in url:
        cid = url.split("/c/")[-1].split()[0]
        for t in tabs:
            if cid[:8] in (t.get("url") or ""):
                tab = t
                break
    if tab is None:
        return None
    try:
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  return JSON.stringify({url: location.href, len: body.length});
})()""", timeout=20)
            return json.loads(raw)
        finally:
            cdp.close()
    except Exception:
        return None


def main():
    log("r4 gate online — clear-signal = fresh chat (r3-w3c) establishing "
        "(/c/ url + growth 2 consecutive cycles) -> relaunch r4-w1 ladder")
    outbox("R4 GATE armed: auto-redispatches the R4-W1 ladder when the "
           "r3-w3c fresh chat establishes itself (the true window-clear "
           "signal).")
    start = time.time()
    streak = 0
    prev_len = None
    while time.time() - start < CAP:
        time.sleep(CYCLE)
        rec = seed_record()
        if rec is None:
            log("seed lane voided/gone — standing down (TL owns redispatch)")
            outbox("R4 GATE: seed lane r3-w3c no longer live — standing down.")
            return 1
        st = lane_state(rec)
        if st is None:
            log("seed lane unprobeable (no tab) — streak reset")
            streak = 0
            continue
        has_chat = "/c/" in (st.get("url") or "")
        grew = prev_len is not None and st.get("len", 0) > prev_len
        prev_len = st.get("len")
        log(f"seed: url={'/c/' if has_chat else 'home'} len={st.get('len')} "
            f"grew={grew} streak={streak}")
        if has_chat and grew:
            streak += 1
            if streak >= 2:
                log("WINDOW TRULY CLEARED — relaunching the r4-w1 ladder")
                outbox("R4 GATE FIRED: r3-w3c established (chat url + "
                       "growth x2) — the window is clear. Relaunching the "
                       "patched r4-w1 dispatch ladder.")
                r = subprocess.run(
                    [sys.executable, os.path.join(BASE, "dfork_launch.py"),
                     os.path.join(BASE, "logs", "dispatch_ladder.log"),
                     sys.executable,
                     os.path.join(BASE, "dispatch_ladder.py")],
                    capture_output=True, text=True, timeout=60, cwd=BASE)
                log(f"ladder relaunch rc={r.returncode}")
                return 0
        else:
            streak = 0
    log("14h cap reached — standing down")
    outbox("R4 GATE CAP: window never cleared in 14h. TL: manual assessment.")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
