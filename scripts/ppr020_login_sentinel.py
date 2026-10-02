#!/usr/bin/env python3
"""ppr020_login_sentinel.py — reset6 epoch (2026-09-29 04:00Z): on operator
login, dispatch PPR-020 (OpenHands) — the sole eligible work order.

State at authoring (04:10 UTC):
  - Sandbox reset6 wiped the local stack; recovered 04:01-04:05
    (console :3000, Chrome CDP :9222, replayd :3100, supervisor ring,
    VPN browser egress 162.19.205.94, PG rail :55432).
  - WAVE K IS CLOSED (frontier-state @ origin/main 3954587):
    PPR-018 (PR #158) + PPR-018A (PR #160) + PPR-019 (PR #161) all
    delivered and merged; currentBase cf4bb49. The overnight successor
    Lead harvested/reconstructed 018A + 019.
  - eligible = [PPR-020] only (OpenHands; deps 018+019+018A closed;
    pre-authorized Tech Lead succession). PPR-016 remains operator-bound.
  - browser_login=logged-out(guest) — operator must log in through the
    replay image before any dispatch can happen.

On login (read-only /api/status poll, 30s cadence, never sends):
  1. check_workspaces.py; stale/Expired rows -> dash_sandbox_release.py
     (reset5 doctrine: release BEFORE assault).
  2. establishment_assault.py ppr020 with the prompt rendered at base
     cf4bb49 (the real work-order send, from inside the replay).
     40-round budget (never-wait doctrine; evening-wall experience).
  3. Outbox every transition; exit 0 when PPR-020 is established and
     queue_watch is armed.

Launch detached: dfork_launch.py /tmp/ppr020_sentinel.log <py> ppr020_login_sentinel.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PROMPTS = os.path.join(BASE, "worker-prompts")

MARKER = "END REPORT"
STATUS_URL = "http://localhost:3000/api/status"
HEARTBEAT = os.path.join(FLAGS, "ppr020_sentinel.heartbeat")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def post(text):
    try:
        os.makedirs(FLAGS, exist_ok=True)
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def run(cmd, timeout=900):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def login_state():
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=8) as r:
            d = json.loads(r.read().decode())
            return d.get("browser_login", "unknown")
    except Exception:
        return "unknown"


def wait_for_login(max_s=16 * 3600):
    t0 = time.time()
    last = None
    while time.time() - t0 < max_s:
        st = login_state()
        if st != last:
            log(f"browser_login={st}")
            last = st
        if st.startswith("logged-in"):
            return True
        try:
            os.makedirs(FLAGS, exist_ok=True)
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
        except Exception:
            pass
        time.sleep(30)
    return False


def release_workspace_slots():
    log("checking workspace slots (reset5 doctrine)...")
    rc, out = run([PY, os.path.join(BASE, "check_workspaces.py")], timeout=180)
    tail = "\n".join((out or "").strip().splitlines()[-6:])
    log(f"check_workspaces rc={rc}:\n{tail}")
    if "Expired" in (out or ""):
        log("stale workspace rows detected -> dash_sandbox_release")
        rc2, out2 = run([PY, os.path.join(BASE, "dash_sandbox_release.py")], timeout=300)
        log(f"dash_sandbox_release rc={rc2}: {(out2 or '').strip()[-200:]}")
        post("PPR-020 sentinel: stale workspace rows released via dash_sandbox_release (slots freed before dispatch).")
    else:
        log("no stale workspace rows detected")


def assault(name, prompt_file, rounds=40):
    pf = os.path.join(PROMPTS, prompt_file)
    log(f"assault[{name}] launching: {prompt_file}")
    post(f"PPR-020 sentinel: dispatching {name} (OpenHands proof, base cf4bb49) via establishment assault — the real work-order send, from inside the replay.")
    rc, out = run([PY, os.path.join(BASE, "establishment_assault.py"),
                   name, pf, MARKER, "360", str(rounds)], timeout=10 * 3600)
    tail = "\n".join((out or "").strip().splitlines()[-3:])
    log(f"assault[{name}] rc={rc}:\n{tail}")
    return rc


def main():
    log("PPR-020 login sentinel start (reset6 epoch, post-wave-K)")
    post("PPR-020 sentinel armed: WAVE K IS CLOSED (018 + 018A + 019 all delivered and merged — PRs #158/#160/#161; currentBase cf4bb49). Next per the roadmap: PPR-020 (OpenHands). Waiting for operator login through the replay image; on login the dispatch fires automatically (stale workspace slots released first).")
    if not wait_for_login():
        post("PPR-020 sentinel: 16h login window elapsed without login — exiting (re-arm on next session).")
        return 4
    log("LOGIN DETECTED — dispatching PPR-020")
    post("LOGIN DETECTED — PPR-020 (OpenHands) dispatch starting.")
    try:
        os.makedirs(FLAGS, exist_ok=True)
        open(os.path.join(FLAGS, "LOGIN_READY"), "w").write(str(int(time.time() * 1000)))
    except Exception:
        pass

    release_workspace_slots()
    rc = assault("ppr020", "ppr-020-openhands-proof.md")

    if rc == 0:
        summary = ("PPR-020 dispatch complete: OpenHands worker ESTABLISHED and generating — "
                   "queue_watch armed, gates on END REPORT. Expected duration 1-3h. "
                   "Next: Lead harvest -> review -> merge at cf4bb49, then PPR-021 (Continue) + "
                   "PPR-022 (Hermes-Agent) become eligible (both depend on 020).")
    else:
        summary = (f"PPR-020 dispatch pass exhausted rounds (rc={rc}) — the account did not "
                   "accept turns within the budget. Standing resident order continues; "
                   "re-arm/re-dispatch follows. Root-cause checks: workspace slots (already "
                   "released above), account rollback-refusal window, capacity wall.")
    log(summary)
    post(summary)
    return rc


if __name__ == "__main__":
    sys.exit(main())
