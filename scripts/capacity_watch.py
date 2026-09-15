#!/usr/bin/env python3
"""capacity_watch.py v2 — detached sentinel for the GLM-5.3 capacity gate.

v1 BUG: the capacity-error text persists in the chat transcript, so a
whole-body includes('at capacity') probe reads TRUE forever. v2 probes the
body TAIL (the last turn's state) AND actively tests the gate with a real
nudge every ACTIVE_EVERY-th probe — the gate is only declared open when a
nudge actually produces generation (or the tail shows fresh content).

When the gate opens: nudges dep-001, launches dep_land loops for
dep-010/020, writes flags/capacity_lifted.marker, exits 0.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
MARKER = os.path.join(BASE, "flags", "capacity_lifted.marker")
DEP001_FRAG = "ec33a313"
PROBE_S = 180
ACTIVE_EVERY = 3   # active nudge test every 3rd probe (~9 min)
MAX_PROBES = 200


def dep001_tab():
    for t in channel.list_tabs():
        if DEP001_FRAG in (t.get("url") or ""):
            return t
    return None


def tail_state(c):
    """Read the LAST turn state from the body tail."""
    try:
        tail = c.eval("document.body.innerText.slice(-300)", await_promise=False, timeout=20) or ""
        stop = c.eval("!!document.querySelector('[class*=stop]')", await_promise=False, timeout=20)
        return {"tail_cap": "at capacity" in tail, "gen": bool(stop), "tail": tail[-120:]}
    except Exception as e:
        return {"err": str(e)[:60]}


def send_nudge(c):
    try:
        c.call("Page.bringToFront", {}, timeout=10)
        c.call("Input.insertText", {"text": "Proceed with the DEP-001 work order now — clone the repo and begin."}, timeout=15)
        time.sleep(1.5)
        c.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter",
                                          "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, timeout=15)
        c.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter",
                                          "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, timeout=15)
        return True
    except Exception as e:
        print(f"nudge ERR {str(e)[:60]}", flush=True)
        return False


def launch_loops():
    for name, prompt in (("dep-010", "worker-prompts/dep-010.md"), ("dep-020", "worker-prompts/dep-020.md")):
        subprocess.Popen(
            [sys.executable, os.path.join(BASE, "dep_land.py"),
             name, os.path.join(BASE, prompt), "75", "15"],
            stdout=open(f"/tmp/dep_land_{name}.log", "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True, cwd=BASE)
        print(f"launched dep_land loop for {name}", flush=True)


def main():
    for i in range(1, MAX_PROBES + 1):
        stamp = time.strftime("%H:%M:%S")
        t = dep001_tab()
        if not t:
            print(f"[{stamp}] probe {i}: dep-001 tab GONE — launching loops + exiting", flush=True)
            launch_loops()
            open(MARKER, "w").write(f"{stamp} tab-gone\n")
            return 0
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=40)
        except Exception as e:
            print(f"[{stamp}] probe {i}: CDP ERR {str(e)[:50]}", flush=True)
            time.sleep(PROBE_S)
            continue
        st = tail_state(c)
        print(f"[{stamp}] probe {i}: cap={st.get('tail_cap')} gen={st.get('gen')}", flush=True)
        if st.get("gen"):
            print("dep-001 GENERATING — launching loops + exiting", flush=True)
            launch_loops()
            open(MARKER, "w").write(f"{stamp} generating\n")
            return 0
        # active gate test every ACTIVE_EVERY-th probe (or when the tail is clean)
        if i % ACTIVE_EVERY == 0 or not st.get("tail_cap"):
            print(f"[{stamp}] active gate test — nudging", flush=True)
            if send_nudge(c):
                time.sleep(18)
                st2 = tail_state(c)
                print(f"[{stamp}] post-nudge: cap={st2.get('tail_cap')} gen={st2.get('gen')} tail={st2.get('tail','')[:80]!r}", flush=True)
                if st2.get("gen"):
                    print("GENERATION STARTED — launching loops + exiting", flush=True)
                    launch_loops()
                    open(MARKER, "w").write(f"{stamp} generating-after-nudge\n")
                    return 0
        try:
            c.close()
        except Exception:
            pass
        time.sleep(PROBE_S)
    print("capacity watch exhausted", flush=True)
    return 4


if __name__ == "__main__":
    sys.exit(main())
