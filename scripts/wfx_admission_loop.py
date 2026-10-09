#!/usr/bin/env python3
"""wfx_admission_loop.py — patient admission loop for quota-stalled lanes.

2026-10-09 23:2xZ situation: three Phase-1 dispatches (d1/d2/d3) admitted
their prompts but never got generation slots (n=0, no stop button, DOM
frozen; nudge via dispatch send also admitted without generating). Pattern
matches the account rolling-usage wall (Task-2/3 doctrine: sequential
re-kicks once the ~1h window clears) — NOT sandbox cap (checked: OK) and
NOT a capacity dialog (none present).

Strategy (w3 canary doctrine, adapted):
  - ONE lane at a time: send a short directive nudge (dispatch_worker send —
    the composer path works, the generation slot is the missing piece),
    wait START_WAIT, truth-check the lane's own tab DOM.
  - LIVE (work markers / stop button / body growth) -> arm the next lane.
  - DEAD -> retry next cycle; after NUDGE_MAX nudges, escalate to
    api_resume.py raw-completions kicks; after RESUME_MAX, flag for TL2.
  - when all lanes are armed: retire to relapse-watch (an armed lane that
    loses generation and has NOT delivered gets re-armed once per cycle);
    the lane-watch daemon separately handles harvest + stall flags.

State: flags/wfx-admission.json (TL2-auditable). Log: logs/wfx-admission.log
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "wfx-admission.log")
LANES = os.path.join(FLAGS, "wfx-lanes.json")
STATE = os.path.join(FLAGS, "wfx-admission.json")
CYCLE = int(os.environ.get("WFX_ADM_CYCLE", "420"))
START_WAIT = int(os.environ.get("WFX_ADM_START_WAIT", "150"))
NUDGE_MAX = 40
RESUME_MAX = 3
PY = sys.executable

NUDGE = ("TL2 directive: your %s work order (base 5549208, contract freeze "
         "v1.0.0) is in this thread above. Begin/resume execution now: setup "
         "per the work order, then the deliverables in order. Narrate progress "
         "as you go. If a tool is missing, say so and stop.")


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_lanes():
    try:
        return [l for l in json.load(open(LANES)) if not l.get("delivered")]
    except Exception:
        return []


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"armed": {}, "nudges": {}, "resumes": {}, "cycles": 0}


def save_state(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE)


def lane_tab(chat_id):
    for t in channel.list_tabs():
        if chat_id in (t.get("url") or ""):
            return t
    return None


def truth_check(chat_id, prev_len=None):
    """LIVE if work markers / stop button / body growth since prev_len."""
    t = lane_tab(chat_id)
    if not t:
        return None, prev_len  # no tab: unknown
    try:
        ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
        try:
            raw = ws.eval(r"""JSON.stringify({
              len: document.body.innerText.length,
              stop: !!document.querySelector('button[class*="stop"]'),
              work: document.body.innerText.includes('Thought Process')
                 || document.body.innerText.includes('Ran ')
                 || document.body.innerText.includes('Terminal')
                 || document.body.innerText.includes('Todo Progress')
            })""", timeout=12)
            d = json.loads(raw)
            grew = prev_len is not None and d["len"] > prev_len + 250
            return (d["stop"] or d["work"] or grew), d["len"]
        finally:
            ws.close()
    except Exception:
        return None, prev_len


def capacity_up(chat_id):
    """True when the lane tab shows a capacity/limit dialog or banner."""
    t = lane_tab(chat_id)
    if not t:
        return False
    try:
        ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=12)
        try:
            raw = ws.eval("JSON.stringify({cap: document.body.innerText.includes('at capacity') || document.body.innerText.includes('peak hours') || document.body.innerText.includes('Limit Sandbox Concurrency'), dlg: !!document.querySelector('[role=dialog]')})", timeout=10)
            d = json.loads(raw)
            return d["cap"] or d["dlg"]
        finally:
            ws.close()
    except Exception:
        return False


def send_nudge(name):
    r = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                        "send", name, NUDGE % name],
                       capture_output=True, text=True, timeout=240)
    out = (r.stdout or "") + (r.stderr or "")
    return "VERIFIED" in out or "verified" in out, out.strip().splitlines()[-1] if out.strip() else ""


def api_kick(chat_id, name):
    msgf = os.path.join(FLAGS, "admission-kick-%s.txt" % name)
    with open(msgf, "w") as f:
        f.write(NUDGE % name)
    r = subprocess.run([PY, os.path.join(BASE, "api_resume.py"),
                        chat_id, msgf], capture_output=True, text=True, timeout=300)
    out = (r.stdout or "") + (r.stderr or "")
    return "ok" in out.lower() or "200" in out, out.strip().splitlines()[-1] if out.strip() else ""


def main():
    log("admission loop online (cycle=%ss start_wait=%ss)" % (CYCLE, START_WAIT))
    while True:
        st = load_state()
        lanes = load_lanes()
        st["cycles"] += 1
        pending = [l for l in lanes if l["name"] not in st["armed"]]
        if not pending:
            # relapse-watch: any armed lane that lost generation and hasn't delivered
            relapsed = []
            for l in lanes:
                live, _ = truth_check(l["chat_id"])
                if live is False:
                    relapsed.append(l)
            if relapsed:
                for l in relapsed:
                    live, _ = truth_check(l["chat_id"])  # re-probe to skip transient
                    if live is False:
                        log("relapse: %s lost generation — re-nudging" % l["name"])
                        ok, tail = send_nudge(l["name"])
                        log("relapse nudge %s: %s | %s" % (l["name"], ok, tail[:90]))
                        if l["name"] in st["armed"]:
                            del st["armed"][l["name"]]
            save_state(st)
            time.sleep(CYCLE)
            continue
        lane = pending[0]
        name, cid = lane["name"], lane["chat_id"]
        prev_live, prev_len = truth_check(cid)
        if prev_live:
            st["armed"][name] = time.time()
            log("%s already live — armed" % name)
            save_state(st)
            continue
        if capacity_up(cid):
            if not st.get("cap_wait"):
                log("capacity wall up — holding nudges for %s (patient wait)" % name)
            st["cap_wait"] = True
            save_state(st)
            time.sleep(CYCLE)
            continue
        if st.get("cap_wait"):
            st["cap_wait"] = False
            log("capacity wall cleared for %s — resuming nudges" % name)
        n = st["nudges"].get(name, 0)
        rk = st["resumes"].get(name, 0)
        if n < NUDGE_MAX:
            ok, tail = send_nudge(name)
            log("nudge %d for %s: send=%s | %s" % (n + 1, name, ok, tail[:90]))
            st["nudges"][name] = n + 1
            time.sleep(START_WAIT)
            live, _ = truth_check(cid, prev_len)
            log("truth-check %s after nudge: live=%s" % (name, live))
            if live:
                st["armed"][name] = time.time()
                log("%s ARMED (generation live)" % name)
            save_state(st)
            continue
        if rk < RESUME_MAX:
            # 2026-10-10 doctrine: raw api kicks spawn TOOL-LESS turns —
            # capacity windows via the composer path are the only real path.
            log("%s nudge budget spent; capacity wait continues (no raw kicks)" % name)
            st["resumes"][name] = RESUME_MAX
            save_state(st)
            time.sleep(CYCLE)
            continue
        if False:
            ok, tail = api_kick(cid, name)
            log("api-resume kick %d for %s: %s | %s" % (rk + 1, name, ok, tail[:90]))
            st["resumes"][name] = rk + 1
            time.sleep(START_WAIT)
            live, _ = truth_check(cid, prev_len)
            if live:
                st["armed"][name] = time.time()
                log("%s ARMED via api-resume" % name)
            save_state(st)
            continue
        # exhausted: flag for TL2, move on to the next lane this cycle
        flag = os.path.join(FLAGS, "%s-admission-blocked" % name)
        if not os.path.exists(flag):
            open(flag, "w").write("nudges=%d resumes=%d ts=%d\n" % (n, rk, time.time()))
            log("%s ADMISSION BLOCKED after %d nudges + %d resumes — TL2 flag set"
                % (name, n, rk))
        save_state(st)
        time.sleep(CYCLE)


if __name__ == "__main__":
    main()
