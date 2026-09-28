#!/usr/bin/env python3
"""restage_assault.py — persistent re-stage sender for the TL2 surge lanes.

Each round: for each lane whose re-stage has NOT landed server-side:
fresh tab -> preflight popup doctrine (dismiss dialogs; Cancel capacity
popups; NEVER switch to Flash) -> insert_and_send -> verify SERVER-SIDE
(the chat tree's user-message count grew — the DOM echo lies) -> close tab.
Backoff between rounds; exits when all lanes landed (or after MAX_ROUNDS).

Sends can be rejected while a generation turn is active (account
serialization under saturation) — the loop simply keeps trying.
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP
import resend_prompt as rp
import chats_http as ch

LANES = [
    ("A", "a0e4ed45-cca4-4651-ae57-8ef01d89c269",
     "/home/z/replay2/scripts/worker-prompts/restage/flauz-tl2-a-restage.md"),
    ("B", "ac121b3f-effd-4cde-941c-ff19960bbf2a",
     "/home/z/replay2/scripts/worker-prompts/restage/flauz-tl2-b-restage.md"),
    ("C", "a48e023b-a372-4e00-bbab-bfe495a79597",
     "/home/z/replay2/scripts/worker-prompts/restage/flauz-tl2-c-restage.md"),
]
LOG = "/home/z/replay2/scripts/logs/restage_assault.log"
MAX_ROUNDS = 40
BACKOFF = 75


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def user_msg_count(cid):
    try:
        rec = ch.api(f"/api/v1/chats/{cid}")
        inner = rec.get("chat", {}) or {}
        msgs = inner.get("history", {}).get("messages", {})
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        return sum(1 for m in msgs if m.get("role") == "user" and m.get("content"))
    except Exception as e:
        log(f"  user_msg_count({cid[:8]}) err: {e}")
        return -1


def attempt(lane, cid, prompt):
    tab = channel.new_tab(f"https://chat.z.ai/c/{cid}")
    if tab is None:
        log(f"[{lane}] no tab")
        return False
    try:
        time.sleep(6)
        cdp = CDP(tab["webSocketDebuggerUrl"], timeout=30)
        d = cdp.eval(rp.JS_DISMISS_DIALOG, timeout=10)
        if d not in ("none",):
            log(f"[{lane}] dialog dismissed: {d}")
            time.sleep(0.8)
        try:
            st = json.loads(cdp.eval(rp.JS_STATE, timeout=15))
            if st.get("capacity") and st.get("hasCancel"):
                log(f"[{lane}] capacity popup -> Cancel (doctrine)")
                cdp.eval(rp.JS_CLICK_CANCEL, timeout=10)
                time.sleep(1.0)
        except Exception as e:
            log(f"[{lane}] state err: {e}")
        pct = rp.insert_and_send(cdp, prompt)
        log(f"[{lane}] sent (insert {pct}%)")
        cdp.close()
    except Exception as e:
        log(f"[{lane}] attempt err: {e}")
    finally:
        try:
            import urllib.request
            urllib.request.urlopen(
                f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
        except Exception:
            pass
    time.sleep(8)  # server settle
    return False


def main():
    origin = {cid: user_msg_count(cid) for _, cid, _ in LANES}
    log(f"=== restage_assault start; baseline user-msgs: " +
        " ".join(f"{l}={origin[c]}" for l, c, _ in LANES))
    for rnd in range(1, MAX_ROUNDS + 1):
        for lane, cid, pfile in LANES:
            n0 = user_msg_count(cid)
            if n0 < 0 or n0 > origin[cid]:
                continue  # errored or already landed
            prompt = open(pfile).read()
            attempt(lane, cid, prompt)
            n1 = user_msg_count(cid)
            if n1 > origin[cid]:
                log(f"[{lane}] LANDED after round {rnd} (user-msgs {origin[cid]}->{n1})")
        if all(user_msg_count(cid) > origin[cid] for _, cid, _ in LANES):
            log("=== all re-stages LANDED; assault exits")
            return
        time.sleep(BACKOFF)
    log(f"=== restage_assault exit after {MAX_ROUNDS} rounds")


if __name__ == "__main__":
    main()
