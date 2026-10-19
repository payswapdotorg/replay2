#!/usr/bin/env python3
"""engine2_kick.py — resident auto-nudger for the hyper3d-engine2 worker.

Platform quirk (2026-10-04 finding): agents-tab turns end after each tool
batch (no autonomous loop); the sandbox filesystem persists progress across
turns. This watcher nudges the worker forward whenever its batch stream goes
static, recovers capacity walls, and exits when BUILD COMPLETE lands.

Primitives used (all battle-tested): batch_tail.py (batch totals + tail),
check_turn_dom.py (stopBtn / banners / capacity text), dispatch_worker.py
send (continuation), capacity_recover_send.py (wall rounds).
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
CID = "2c6441c6-6ad8-4b9b-8628-a7c70d452354"
NAME = "hyper3d-engine2"
SUB = "2c6441c6"
HB = os.path.join(BASE, "flags", "engine2_kick_hb")
LOG = os.path.join(BASE, "logs", "engine2_kick.log")
NUDGE = (
    "Continue autonomously — execute your Final Implementation Plan without "
    "stopping between tool batches (the platform ends turns after each batch; "
    "keep working straight through them). Your sandbox filesystem persists all "
    "progress. Only stop to emit the FINAL REPORT format when every gate passes."
)


def log(msg):
    line = f"[engine2_kick {time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


def run(cmd, timeout=240):
    try:
        r = subprocess.run(
            [sys.executable] + cmd, capture_output=True, text=True,
            timeout=timeout, cwd=BASE)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return f"__ERR__ {e}"


def batch_state():
    out = run(["batch_tail.py", CID, "2"], timeout=120)
    head = out.splitlines()[0] if out.splitlines() else ""
    done = "BUILD COMPLETE" in out
    try:
        total = int(head.split("totalLen:")[1].split()[0])
    except Exception:
        total = -1
    return total, done, out


def turn_state():
    out = run(["check_turn_dom.py", CID], timeout=120)
    try:
        d = json.loads(out[out.index("{"):])
        return d.get("stopBtn"), (d.get("tail") or "")
    except Exception:
        return None, ""


def reopen_tab():
    """Roll-home self-heal: the SPA sometimes rolls the worker tab home
    ('chat destroyed' class); the thread lives server-side. Reopen it."""
    try:
        import channel
        tab = channel.new_tab(f"https://chat.z.ai/c/{CID}")
        log(f"tab reopened: {tab.get('id') if tab else 'FAILED'}")
        return tab is not None
    except Exception as e:
        log(f"tab reopen failed: {e}")
        return False


def main():
    last_total = -1
    static = 0
    probe_fails = 0
    log(f"armed for {NAME} cid={CID}")
    while True:
        time.sleep(360)
        total, done, out = batch_state()
        if total < 0 and done is False and "totalLen" not in out:
            probe_fails += 1
            if probe_fails >= 3:
                log(f"{probe_fails} consecutive probe failures — reopening tab")
                if reopen_tab():
                    probe_fails = 0
                else:
                    probe_fails = 2  # retry reopen next round
            else:
                log("batch probe failed — skipping round")
            with open(HB, "w") as f:
                f.write(f"{int(time.time())} total={total} static={static} done={done} probefails={probe_fails}")
            continue
        probe_fails = 0
        with open(HB, "w") as f:
            f.write(f"{int(time.time())} total={total} static={static} done={done}")
        if done:
            log("BUILD COMPLETE in batch — watcher exiting")
            return
        if total < 0:
            log("batch probe failed — skipping round")
            continue
        if total == last_total:
            static += 1
        else:
            log(f"batch growing: {last_total} -> {total}")
            static = 0
        last_total = total
        if static < 2:
            continue
        stop, tail = turn_state()
        log(f"static x{static} stopBtn={stop} tailcap={'peak hours' in tail}")
        if stop:
            log("still generating (stopBtn) — wait more")
            continue
        if "peak hours" in tail:
            rec = run(["capacity_recover_send.py", SUB], timeout=300)
            log("capacity recovery fired: " + rec.strip().splitlines()[-1][:120]
                if rec.strip() else "capacity recovery: no output")
            static = 0
            continue
        r = run(["dispatch_worker.py", "send", NAME, NUDGE], timeout=300)
        last = r.strip().splitlines()[-1] if r.strip() else "no output"
        log(f"nudge sent: {last[:120]}")
        static = 0


if __name__ == "__main__":
    main()
