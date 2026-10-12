#!/usr/bin/env python3
"""unicom_landing_loop.py — the continuation-send fight machine (the banked
W1-016-era law): per cycle, probe the lane's chat server-side; if the order
has NOT landed (message count unchanged + leaf turn unchanged), run the
dispatch_worker send ladder once; verify server-side; exit 0 on LANDED.

LANDED (the server-truth law — DOM readbacks are advisory): the chat's
message count grew past BASE_N AND the leaf turn moved past BASE_LEAF.

Usage: unicom_landing_loop.py <lane-name> <chat-uuid> <order-file> <base-n> <base-leaf-prefix> [cycles] [cadence-s]
Detached-safe (dfork_launch.py). Logs to logs/<lane-name>_landing.log.
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import chats_http  # noqa: E402

CYCLES = 45
CADENCE_S = 150


def log(msg):
    print(f"[landing {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def chat_state(chat_id):
    d = chats_http.api(f"/api/v1/chats/{chat_id}")
    if isinstance(d, dict) and "data" in d:
        d = d["data"]
    c = d.get("chat", d)
    hist = c.get("history", {}).get("messages", {})
    msgs = sorted(hist.values(), key=lambda m: m.get("timestamp", 0))
    n = len(msgs)
    leaf = msgs[-1]["id"] if msgs else ""
    return n, leaf


def main():
    lane, chat_id, order_file = sys.argv[1], sys.argv[2], sys.argv[3]
    base_n, base_leaf = int(sys.argv[4]), sys.argv[5]
    cycles = int(sys.argv[6]) if len(sys.argv) > 6 else CYCLES
    cadence = int(sys.argv[7]) if len(sys.argv) > 7 else CADENCE_S

    log(f"armed: lane={lane} base_n={base_n} base_leaf={base_leaf[:8]} "
        f"cycles={cycles} cadence={cadence}s")

    for i in range(cycles):
        try:
            n, leaf = chat_state(chat_id)
        except Exception as e:
            log(f"cycle {i}: probe error {e!r} — retrying next cycle")
            time.sleep(cadence)
            continue
        if n > base_n and not leaf.startswith(base_leaf):
            log(f"LANDED: n={n} (>{base_n}), leaf={leaf[:8]} (moved off {base_leaf[:8]}) — exiting 0")
            return 0
        # not landed: one send-ladder attempt
        r = subprocess.run(
            ["python3", os.path.join(BASE, "dispatch_worker.py"),
             "send", lane, f"@{order_file}"],
            capture_output=True, text=True, timeout=280,
        )
        tail = (r.stdout or "").strip().splitlines()
        last = tail[-1] if tail else (r.stderr or "").strip().splitlines()[-1:]
        log(f"cycle {i}: send attempt -> {last if last else 'no output'}")
        time.sleep(7)
        try:
            n2, leaf2 = chat_state(chat_id)
            if n2 > base_n and not leaf2.startswith(base_leaf):
                log(f"LANDED: n={n2} (>{base_n}), leaf={leaf2[:8]} — exiting 0")
                return 0
        except Exception as e:
            log(f"cycle {i}: post-send probe error {e!r}")
        time.sleep(cadence)
    log(f"window exhausted ({cycles} cycles) — NOT landed; the TL re-arms")
    return 1


if __name__ == "__main__":
    sys.exit(main())
