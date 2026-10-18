#!/usr/bin/env python3
"""saturation_gate.py — wait for the generation-saturation window to clear,
then relaunch the (patched) r4-w1 dispatch ladder (Task 85, 2026-10-18).

The 17:20Z+ window: every generation attempt on ANY chat returns
'No response, Please try again later.' + the site's own fetches return
HTML error pages. Fresh chats get ROLLED BACK (landing page). The current
ladder will burn its remaining attempts into this window and stand down.

Gate law:
  - probe mer-B (the established chat) every 300s
  - CLEAR = noresp=False AND (stopBtn OR streaming OR body growth vs prev)
  - two consecutive CLEAR probes = window open -> void the dead r4-w1
    chats -> relaunch dispatch_ladder.py (patched: registry URL parse)
  - slow-pulse nudge: if mer-B shows noresp on 2 consecutive cycles, send
    a light nudge every 2nd cycle (the renudge loop's 12-budget exhausts
    in a long window; this keeps a pulse without hammering)
  - 3h cap -> outbox notify + stand down

Launch: dfork_launch.py logs/saturation_gate.log <venv-py> saturation_gate.py
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
LOG = os.path.join(BASE, "logs", "saturation_gate.log")
CYCLE = 300
CAP_SECONDS = 3 * 3600
MERB = "7b4c016d-4410-4a43-967d-fa597b14e615"
DEAD_R4 = ["payswap3-r4-w1b", "payswap3-r4-w1c", "payswap3-r4-w1d",
           "payswap3-r4-w1e"]
NUDGE = ("Continue the work order from where you stopped. "
         "(auto-nudge: generation dropped; resume your current wave)")


def log(msg):
    print(time.strftime("[%m-%d %H:%M:%S] ") + str(msg), flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def run(cmd, timeout=290):
    try:
        r = subprocess.run([sys.executable] + cmd, capture_output=True,
                           text=True, timeout=timeout, cwd=BASE)
        return (r.stdout or "").strip().splitlines()
    except subprocess.TimeoutExpired:
        return ["timeout"]


def merb_state():
    tab = channel.find_tab(MERB)
    if tab is None:
        return {"tab": False}
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const streaming = ['Thinking', 'Generating', 'typing…', 'Thought Process'].some(m => body.includes(m));
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const noresp = body.includes('No response');
  return JSON.stringify({tab: true, streaming, stopBtn, noresp, len: body.length});
})()""", timeout=20)
        return json.loads(raw)
    except Exception as e:
        return {"tab": True, "err": str(e)[:80]}
    finally:
        cdp.close()


def ladder_alive():
    try:
        r = subprocess.run(["pgrep", "-f", "dispatch_ladder.py"],
                           capture_output=True, text=True, timeout=10)
        # exclude our own pgrep match and this script's process
        return bool(r.stdout.strip())
    except Exception:
        return False


def main():
    log("saturation gate online — watching mer-B for window-clear "
        f"(2 consecutive clean probes), {CAP_SECONDS//60}min cap")
    outbox("R4-W1 saturation gate armed: watches mer-B for generation "
           "recovery, then voids dead r4-w1 chats + relaunches the patched "
           "ladder. Slow-pulse nudges mer-B while the window persists.")
    start = time.time()
    clear_streak = 0
    prev_len = None
    noresp_streak = 0
    pulse_count = 0
    launched = False

    while time.time() - start < CAP_SECONDS:
        time.sleep(CYCLE)
        st = merb_state()
        if st.get("err") or not st.get("tab"):
            log(f"probe issue: {st.get('err') or 'no tab'}")
            clear_streak = 0
            continue

        grew = (prev_len is not None and st["len"] > prev_len)
        prev_len = st["len"]
        active = st.get("stopBtn") or st.get("streaming") or grew
        clear = (not st.get("noresp")) and active

        log(f"mer-B: len={st['len']} noresp={st.get('noresp')} "
            f"stopBtn={st.get('stopBtn')} streaming={st.get('streaming')} "
            f"grew={grew} clear-streak={clear_streak}")

        if clear:
            clear_streak += 1
            if clear_streak >= 2 and not launched:
                log("WINDOW CLEARED (2 consecutive clean probes) — "
                    "relaunching the patched r4-w1 ladder")
                outbox("SATURATION WINDOW CLEARED: mer-B is generating "
                       "again. Voiding dead r4-w1 chats + relaunching the "
                       "patched dispatch ladder.")
                # kill the OLD-code ladder first (its URL-parse bug makes it
                # abandon every chat it creates; two concurrent ladders =
                # the duplicate-worker class). Its already-sent chats are
                # adopted by the relaunched ladder via adopt_live().
                subprocess.run(["pkill", "-f", "dispatch_ladder.py"],
                               capture_output=True, timeout=15)
                time.sleep(3)
                for name in DEAD_R4:
                    run([os.path.join(BASE, "dispatch_worker.py"), "void",
                         name, "saturation rollback (gate cleanup)"])
                    log(f"voided {name}")
                # canonical daemon launch: double-fork via dfork_launch.py
                r = subprocess.run(
                    [sys.executable, os.path.join(BASE, "dfork_launch.py"),
                     os.path.join(BASE, "logs", "dispatch_ladder.log"),
                     sys.executable,
                     os.path.join(BASE, "dispatch_ladder.py")],
                    capture_output=True, text=True, timeout=60, cwd=BASE)
                log(f"ladder relaunch rc={r.returncode}")
                launched = True
                log("ladder relaunched; gate stands down")
                outbox("R4-W1 ladder relaunched (patched URL parsing). "
                       "Gate standing down.")
                return 0
        else:
            clear_streak = 0

        # slow-pulse nudge while saturated
        if st.get("noresp"):
            noresp_streak += 1
            if noresp_streak % 2 == 0:
                pulse_count += 1
                lines = run([os.path.join(BASE, "dispatch_worker.py"), "send",
                             "payswap3-r3-w3b", NUDGE])
                v = lines[-1] if lines else "?"
                log(f"slow-pulse nudge #{pulse_count}: {v[:80]}")
        else:
            noresp_streak = 0

    log("3h cap reached — standing down")
    outbox("SATURATION GATE CAP: window never cleared in 3h. TL: manual "
           "assessment needed (site-side outage class?).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
