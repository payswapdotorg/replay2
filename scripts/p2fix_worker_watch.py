#!/usr/bin/env python3
"""p2fix_worker_watch.py — resident completion watch for the p2fix-d worker.

Field laws applied (Task-17 liveness + w090c completion + Task-18 nudges):
  - OWN-tab probe at the worker chat URL; the tab is the source of truth.
  - Liveness: growth in EITHER the thinking-chain DOM
    (.thinking-chain-container — reasoning_effort=max streams thinking
    long before the message body grows) OR the body text length.
  - Completion = the UN-FORGEABLE signature: a 'P2FIX-D COMPLETION
    REPORT' block followed by THREE real 40-hex commit shas on the three
    named branches. The echoed packet template carries '<full 40-hex sha>'
    placeholders and can never match (the w090c false-positive lesson).
  - Stall (30 min zero growth): auto-nudge continuation (packet rule 5,
    max 3), outbox note each time.
  - On completion: flags/p2fix_d_done.json + outbox + exit (harvest is the
    TL's next move).
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
DONE_FLAG = os.path.join(FLAGS, "p2fix_d_done.json")

WORKER_CHAT_URL = "https://chat.z.ai/c/70b71ed7-e06a-4022-b886-a96ba88c24a0"
WORKER_CHAT_ID = "70b71ed7-e06a-4022-b886-a96ba88c24a0"

CYCLE_S = 90
STALL_S = 30 * 60
MAX_NUDGES = 3

REAL_REPORT_RE = re.compile(
    r"P2FIX-D COMPLETION REPORT[\s\S]{0,600}?"
    r"branch flauz-p2fix/p2-fix-201:\s*commit\s+[0-9a-f]{40}"
    r"[\s\S]{0,200}?branch flauz-p2fix/p2-fix-202:\s*commit\s+[0-9a-f]{40}"
    r"[\s\S]{0,200}?branch flauz-p2fix/p2-fix-205:\s*commit\s+[0-9a-f]{40}")

NUDGE_MSG = (
    "[TL rescue] Continue the P2-FIX partition D work order autonomously "
    "from exactly where you left off. Do not re-introduce yourself and do "
    "not restart finished work. Finish the remaining branches (the three "
    "minimal diffs exactly as specified), run the gate set on each branch, "
    "write harvest-d/ + MANIFEST.json with the REAL commit shas, then end "
    "your final message with the exact 'P2FIX-D COMPLETION REPORT' block "
    "from the work order with the three REAL 40-hex commit shas (never "
    "the template placeholders).")

PROBE_JS = r"""(() => {
  const think = document.querySelector('.thinking-chain-container');
  const txt = document.body.innerText || '';
  const gen = !!(document.querySelector('img[class*=loading], [class*=generating], [role=status]'));
  return JSON.stringify({
    url: location.href,
    bodyLen: txt.length,
    thinkLen: think ? think.textContent.length : 0,
    generating: gen,
    tail: txt.slice(-160)
  });
})()"""


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def outbox(text):
    os.makedirs(FLAGS, exist_ok=True)
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def own_tab():
    for t in channel.list_tabs():
        if WORKER_CHAT_ID in (t.get("url") or ""):
            return t
    try:
        t = channel.new_tab(WORKER_CHAT_URL)
        time.sleep(8)
        return t
    except Exception as e:
        log("tab open failed: %s" % e)
        return None


def probe():
    """(body_text, state) from the worker tab, or (None, None)."""
    tab = own_tab()
    if not tab:
        return None, None
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            txt = c.eval("(document.body.innerText || '')", timeout=30) or ""
            st = None
            try:
                v = c.eval(PROBE_JS, timeout=30)
                st = json.loads(v) if v else None
            except Exception:
                pass
            return txt, st
        finally:
            c.close()
    except Exception as e:
        log("probe failed: %s" % e)
        return None, None


def send_nudge():
    try:
        res = channel.send_text(NUDGE_MSG)
        ok = bool(res.get("ok"))
        log("nudge send ok=%s detail=%s" % (ok, res.get("detail", "")))
        return ok
    except Exception as e:
        log("nudge send error: %s" % e)
        return False


def main():
    if os.path.exists(DONE_FLAG):
        log("p2fix-d already done — exiting")
        return 0
    log("resident watch armed: %s (cycle %ss, stall %ss, max nudges %d)"
        % (WORKER_CHAT_ID, CYCLE_S, STALL_S, MAX_NUDGES))
    last_sig = None       # (bodyLen, thinkLen)
    last_growth = time.time()
    nudges = 0
    while True:
        txt, st = probe()
        if txt is None:
            time.sleep(CYCLE_S)
            continue

        # completion: the un-forgeable three-sha signature
        m = REAL_REPORT_RE.search(txt)
        if m:
            block = m.group(0)
            shas = re.findall(r"commit ([0-9a-f]{40})", block)
            log("REAL COMPLETION REPORT detected: shas %s" % shas)
            with open(DONE_FLAG, "w") as f:
                json.dump({"ts": int(time.time()), "shas": shas,
                           "chat": WORKER_CHAT_ID,
                           "report_tail": txt[m.start():m.start() + 700]}, f, indent=1)
            outbox("p2fix-d REAL COMPLETION REPORT detected (three 40-hex "
                   "commit shas: %s). Worker lane complete — the TL "
                   "station will harvest harvest-d/, reconstruct the three "
                   "branches, re-verify and run the merge wave."
                   % ", ".join(s[:10] for s in shas))
            return 0

        # liveness: growth in thinking DOM or body
        sig = (len(txt), (st or {}).get("thinkLen", 0))
        if last_sig is not None and sig != last_sig:
            last_growth = time.time()
            if sig[1] != last_sig[1] or sig[0] != last_sig[0]:
                log("alive: body %d->%d think %d->%d tail=%r"
                    % (last_sig[0], sig[0], last_sig[1], sig[1],
                       ((st or {}).get("tail") or "")[:80]))
        last_sig = sig

        # stall -> nudge (packet rule 5)
        if time.time() - last_growth > STALL_S:
            if nudges < MAX_NUDGES:
                nudges += 1
                log("STALLED %.0f min — sending continuation nudge %d/%d"
                    % ((time.time() - last_growth) / 60, nudges, MAX_NUDGES))
                outbox("p2fix-d stalled %.0f min (zero growth in thinking "
                       "DOM and body) — auto-nudge %d/%d sent per packet "
                       "rule 5." % ((time.time() - last_growth) / 60, nudges, MAX_NUDGES))
                send_nudge()
                last_growth = time.time()  # give the nudge a full stall window
            else:
                log("STALLED with nudges exhausted — flagging for TL pickup")
                outbox("p2fix-d stalled with all %d nudges exhausted — the "
                       "TL will inspect on next pickup." % MAX_NUDGES)
                with open(os.path.join(FLAGS, "p2fix_d_stalled.json"), "w") as f:
                    json.dump({"ts": int(time.time()), "nudges": nudges,
                               "last_sig": list(last_sig or (0, 0))}, f)
                last_growth = time.time()

        time.sleep(CYCLE_S)


if __name__ == "__main__":
    sys.exit(main())
