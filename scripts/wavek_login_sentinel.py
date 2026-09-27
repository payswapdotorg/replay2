#!/usr/bin/env python3
"""wavek_login_sentinel.py — reset5 epoch (2026-09-27): on operator login,
resume wave-K of the Zeck compatibility roadmap (midnight deadline).

State at authoring (11:00 UTC):
  - Sandbox reset5 at 10:42 wiped the local stack; recovered 10:54-10:57.
  - PPR-018 was dispatched 09:42:40 as chat f978ac52-61ab-4159-bc10-d3150b23a1fa
    (established, generating at 09:45). Workers run SERVER-SIDE — the reset
    did NOT touch it. Unknown: completed / still running / turn-died.
  - Frontier at main b35d7e8 (reconciled by the Architect 10:00):
    eligible = PPR-018A + PPR-018 + PPR-019 (three-worker wave,
    maxConcurrentWorkers=3); PPR-020+ gated on all three.

On login (read-only /api/status poll, 30s cadence, never sends):
  1. probe f978ac52 server-side (full-UUID law) with marker END REPORT:
     - reportInAssistant -> PPR-018 COMPLETE server-side; outbox; Lead
       harvests (no slot consumed);
     - alive, no marker, activity fresh (<40 min) -> re-open its tab,
       arm queue_watch[ppr018];
     - dead / not found -> re-dispatch with ppr018-aider-proof-r2.md.
  2. check_workspaces.py; if the 3-slot limit is held by stale rows ->
     dash_sandbox_release.py (reset5 doctrine: release BEFORE assault).
  3. Sequential establishment assaults (the proven dispatch machinery,
     driven from inside the replay): ppr018a, ppr019, then ppr018 (r2,
     only if not already handled). Each: 16-round budget, END REPORT
     marker, queue_watch auto-armed on establishment.
  4. Outbox every transition; exit 0 when the wave is armed.

Launch detached: dfork_launch.py /tmp/wavek_sentinel.log <py> wavek_login_sentinel.py
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

PPR018_CHAT = "f978ac52-61ab-4159-bc10-d3150b23a1fa"
MARKER = "END REPORT"
STATUS_URL = "http://localhost:3000/api/status"
FRESH_ACTIVITY_S = 40 * 60  # a worker turn quiet for >40 min with no marker is dead
HEARTBEAT = os.path.join(FLAGS, "wavek_sentinel.heartbeat")


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


def wait_for_login(max_s=4 * 3600):
    t0 = time.time()
    last = None
    while time.time() - t0 < max_s:
        st = login_state()
        if st != last:
            log(f"browser_login={st}")
            last = st
        if st == "logged-in":
            return True
        try:
            os.makedirs(FLAGS, exist_ok=True)
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
        except Exception:
            pass
        time.sleep(30)
    return False


def probe(uuid, marker=MARKER):
    rc, out = run([PY, os.path.join(BASE, "probe_chat.py"), uuid, marker], timeout=120)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def handle_ppr018():
    """Returns True if PPR-018 is already handled (complete or watched)."""
    log(f"probing PPR-018 chat {PPR018_CHAT} (server-side truth)...")
    d = probe(PPR018_CHAT)
    if d is None or not d.get("alive"):
        log("PPR-018 chat not found / probe failed -> will re-dispatch r2")
        post("wave-K sentinel: PPR-018 chat f978ac52 absent server-side (rolled back or probe denied) -> re-dispatch planned with base b35d7e8.")
        return False
    msgs = int(d.get("msgs", -1))
    age = (int(d.get("now", 0)) - int(d.get("updated", 0))) if d.get("updated") else -1
    if d.get("reportInAssistant"):
        log("PPR-018 COMPLETE server-side (END REPORT present)")
        post("wave-K: PPR-018 chat f978ac52 carries the END REPORT server-side — COMPLETE. Lead harvest path next (pod tree -> tarball -> battery -> merge). No re-dispatch, no slot consumed.")
        return True
    if msgs >= 2 and 0 <= age < FRESH_ACTIVITY_S:
        log(f"PPR-018 alive (msgs={msgs}, age={age}s) -> re-open tab + arm watch")
        rc, out = run([PY, os.path.join(BASE, "reopen_and_watch.py"), PPR018_CHAT, "ppr018", MARKER], timeout=300)
        log(f"reopen_and_watch rc={rc}: {(out or '').strip()[-200:]}")
        if rc == 0:
            post("wave-K: PPR-018 chat f978ac52 still alive server-side (msgs>=2, fresh activity) — tab re-opened, queue_watch[ppr018] re-armed. Wave slot held by the live run.")
            return True
        log("reopen_and_watch failed -> treating as needing re-dispatch")
        return False
    log(f"PPR-018 dead turn (msgs={msgs}, age={age}s, no marker) -> will re-dispatch r2")
    post(f"wave-K: PPR-018 chat f978ac52 turn-dead (msgs={msgs}, quiet {age}s, no END REPORT) -> re-dispatch r2 planned.")
    return False


def release_workspace_slots():
    log("checking workspace slots (reset5 doctrine)...")
    rc, out = run([PY, os.path.join(BASE, "check_workspaces.py")], timeout=180)
    tail = "\n".join((out or "").strip().splitlines()[-6:])
    log(f"check_workspaces rc={rc}:\n{tail}")
    full = ("limit" in (out or "") and "total" in (out or ""))
    # crude fullness heuristic: the dashboard list shows Expired rows
    if "Expired" in (out or "") or full:
        log("stale workspace rows detected -> dash_sandbox_release")
        rc2, out2 = run([PY, os.path.join(BASE, "dash_sandbox_release.py")], timeout=300)
        log(f"dash_sandbox_release rc={rc2}: {(out2 or '').strip()[-200:]}")
        post("wave-K: stale workspace rows released via dash_sandbox_release (reset5 doctrine — slots freed before assault).")
    else:
        log("no stale workspace rows detected")


def assault(name, prompt_file, rounds=16):
    pf = os.path.join(PROMPTS, prompt_file)
    log(f"assault[{name}] launching: {prompt_file}")
    post(f"wave-K: dispatching {name} ({prompt_file}) via establishment assault — the real work-order send, from inside the replay.")
    rc, out = run([PY, os.path.join(BASE, "establishment_assault.py"),
                   name, pf, MARKER, "360", str(rounds)], timeout=6 * 3600)
    tail = "\n".join((out or "").strip().splitlines()[-3:])
    log(f"assault[{name}] rc={rc}:\n{tail}")
    return rc


def main():
    log("wave-K login sentinel start (reset5 epoch)")
    post("wave-K sentinel armed: waiting for operator login through the replay image. On login: probe PPR-018 (f978ac52), release stale workspace slots if any, then dispatch PPR-018A + PPR-019 (+ PPR-018 r2 only if the old chat is dead). Midnight deadline plan.")
    if not wait_for_login():
        post("wave-K sentinel: 4h login window elapsed without login — exiting (re-arm on next session).")
        return 4
    log("LOGIN DETECTED — resuming wave-K")
    post("LOGIN DETECTED — wave-K resumption starting.")
    try:
        os.makedirs(FLAGS, exist_ok=True)
        open(os.path.join(FLAGS, "LOGIN_READY"), "w").write(str(int(time.time() * 1000)))
    except Exception:
        pass

    ppr018_handled = handle_ppr018()
    release_workspace_slots()

    results = {}
    results["ppr018a"] = assault("ppr018a", "ppr-018a-runner-harness.md")
    results["ppr019"] = assault("ppr019", "ppr-019-cline-proof.md")
    if not ppr018_handled:
        results["ppr018"] = assault("ppr018", "ppr018-aider-proof-r2.md")

    ok = [k for k, v in results.items() if v == 0]
    bad = [k for k, v in results.items() if v != 0]
    summary = (f"wave-K dispatch pass complete: established={ok or 'none'}"
               f"{'; exhausted-rounds=' + ','.join(bad) if bad else ''}. "
               f"PPR-018 prior chat: {'complete/watched' if ppr018_handled else 're-dispatched (or assault exhausted)'}. "
               f"Watch ring armed per established session; queue_watch gates on END REPORT.")
    log(summary)
    post(summary)
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
