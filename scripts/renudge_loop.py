#!/usr/bin/env python3
"""renudge_loop.py — peak-hours generation recovery (Task 84, 2026-10-18).

Both live chats (mer-B + r4-w1) sit at 'No response, Please try again
later.' — the site-side generation queue is saturated (their own fetches
return HTML error pages). Each nudge = a fresh generation attempt; the
proven assault law: never wait passively, but never interrupt a live
stream. This loop:
  - every 240s: check each chat for streaming markers
  - if frozen + 'No response': send a SHORT nudge via dispatch_worker send
  - log everything; stop nudging a chat once it streams
Launch: dfork_launch.py logs/renudge_loop.log <venv-py> renudge_loop.py
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "renudge_loop.log")
CYCLE = 300
MAX_NUDGES_PER_CHAT = 12
SEND_TIMEOUT = 290   # the dispatcher send can take >110s under browser
                    # contention (watch + probes share Chrome); reading the
                    # verdict beats re-nudging blind

CHATS = {
    "7b4c016d": {"name": "payswap3-r3-w3b", "label": "mer-B"},
    "07f7cac8": {"name": "payswap3-r4-w1", "label": "r4-w1 lab"},
}

NUDGE = ("Continue the work order from where you stopped. "
         "(auto-nudge: generation dropped; resume your current wave)")


def log(msg):
    line = time.strftime("[%m-%d %H:%M:%S] ") + str(msg)
    print(line, flush=True)


def chat_state(cid):
    tab = channel.find_tab(cid)
    if tab is None:
        return {"tab": False}
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const streaming = ['Thinking', 'Generating', 'typing…'].some(m => body.includes(m));
  const noresp = body.includes('No response');
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  return JSON.stringify({tab: true, streaming, noresp, stopBtn, len: body.length});
})()
""", timeout=20)
        return json.loads(raw)
    except Exception as e:
        return {"tab": True, "err": str(e)[:80]}
    finally:
        cdp.close()


def main():
    counts = {cid: 0 for cid in CHATS}
    log("renudge loop online — chats: " + ", ".join(f"{v['label']}({k[:8]})" for k, v in CHATS.items()))
    for rounds in range(200):  # ~13h max
        for cid, meta in CHATS.items():
            st = chat_state(cid)
            if not st.get("tab"):
                log(f"{meta['label']}: no tab (skip)")
                continue
            if st.get("err"):
                log(f"{meta['label']}: probe error {st['err']}")
                continue
            if st.get("streaming") or st.get("stopBtn"):
                log(f"{meta['label']}: STREAMING (len={st.get('len')}) — no nudge")
                counts[cid] = 0
                continue
            if not st.get("noresp"):
                log(f"{meta['label']}: no 'No response' marker (len={st.get('len')}) — leaving alone")
                continue
            if counts[cid] >= MAX_NUDGES_PER_CHAT:
                log(f"{meta['label']}: nudge budget exhausted")
                continue
            # frozen + no-response: nudge via dispatcher
            try:
                r = subprocess.run(
                    [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                     "send", meta["name"], NUDGE],
                    capture_output=True, text=True, timeout=SEND_TIMEOUT)
                out = (r.stdout or "").strip().splitlines()
                verdict = out[-1] if out else f"rc={r.returncode}"
                counts[cid] += 1
                log(f"{meta['label']}: NUDGE #{counts[cid]} -> {verdict[:90]}")
            except Exception as e:
                log(f"{meta['label']}: nudge failed {str(e)[:80]}")
        time.sleep(CYCLE)
    log("renudge loop window expired")


if __name__ == "__main__":
    main()
