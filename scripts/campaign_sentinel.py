#!/usr/bin/env python3
"""campaign_sentinel.py — v2 autonomous dispatch fighter (2026-09-25).

Successor of peak_sentinel.py: fights the platform sandbox-pool starvation
for BOTH remaining RoamLink work orders (PA-018 F-016-1, PA-019 F-016-2),
serialized per boot lesson 142 (paced, ride-to-generation):

  PROBE phase: every cycle, patient-dispatch a sandbox canary (echo probe);
    if it REPLIED the pool is admitting -> delete the canary chat and enter
    the WO phase inside the admit-window (the canary play, Task-102).
  PA018 phase: patient-dispatch PA-018 (fresh name per attempt, serialized),
    ride the landing to GENERATION (poll server-side). A 0-message tree
    after landing = REAPED -> pace WO_PACE_S and retry with a fresh name.
    On GENERATING: log loudly, pace, advance to PA019.
  PA019 phase: identical ride with PA-019.md. On GENERATING: SUCCESS exit 0.

v2 fixes over v1: corpse detection (a reaped chat still answers 200 on
detail with an EMPTY message tree — v1 read that as 'queued' forever);
PA-019 is in the fight (v1 only watched a dead held chat); canary chats
are deleted after use (surface hygiene, lesson 135 awareness).

Exit: 0 both WOs generating; 1 MAX_HOURS reached; 2 config error.
Everything lands in scripts/logs/campaign_sentinel.log.
"""
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chats_http  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "campaign_sentinel.log")
PY = sys.executable
CANARY_PROMPT = os.path.join(BASE, "worker-prompts", "SANDBOX-CANARY.md")
WOS = [
    ("pa018", os.path.join(BASE, "worker-prompts", "PA-018.md")),
    ("pa019", os.path.join(BASE, "worker-prompts", "PA-019.md")),
]
CYCLE_S = int(os.environ.get("CYCLE_S", "720"))
WO_PACE_S = int(os.environ.get("WO_PACE_S", "900"))
GEN_WATCH_S = int(os.environ.get("GEN_WATCH_S", "2400"))
MAX_HOURS = float(os.environ.get("MAX_HOURS", "6"))


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def chat_rows(cid):
    """Message rows via the chats API, or None on error."""
    try:
        d = chats_http.api(f"/api/v1/chats/{cid}")
        rec = d.get("data", d) if isinstance(d, dict) else {}
        inner = rec.get("chat", {}) or rec
        msgs = (inner.get("history", {}) or {}).get("messages", {})
        rows = list(msgs.values()) if isinstance(msgs, dict) else (msgs or [])
        return rows if isinstance(rows, list) else []
    except Exception:
        return None


def chat_state(cid):
    """GENERATING | spawned | queued | reaped | err."""
    rows = chat_rows(cid)
    if rows is None:
        return "err"
    if not rows:
        return "reaped"  # the v1 blind spot: empty tree = destroyed packet
    if any(m.get("generating") for m in rows):
        return "GENERATING"
    if any(m.get("role") == "assistant" for m in rows):
        return "spawned"
    return "queued"


def run(cmd, timeout_s):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def patient_create(name, prompt):
    """launch_patient; poll its log for SENT-VERIFIED / FAILED (serialized)."""
    logf = os.path.join(BASE, "logs", f"create_{name}.log")
    r = run([PY, os.path.join(BASE, "launch_patient.py"), name, prompt], 60)
    if r[0] != 0:
        log(f"patient launch failed for {name}: {r[1][-120:]}")
        return None
    for _ in range(42):  # up to ~7 min
        time.sleep(10)
        try:
            tail = open(logf).read()[-2500:]  # whole file (small); 400 chars missed long tracebacks
        except Exception:
            continue
        m = re.search(r"SENT-VERIFIED \(server\): chat ([0-9a-f-]{36})", tail)
        if m:
            return m.group(1)
        if ("send FAILED server-side" in tail or "Traceback" in tail
                or "aborting BEFORE phantom create" in tail
                or "send button never enabled" in tail
                or "WebSocketTimeoutException" in tail
                or "Connection timed out" in tail):
            return None
    return None


def canary_replied(cid, budget_s=240):
    deadline = time.time() + budget_s
    while time.time() < deadline:
        rows = chat_rows(cid)
        if rows:
            for m in rows:
                c = m.get("content")
                if m.get("role") == "assistant" and isinstance(c, str) and "SANDBOX-POOL-OK" in c:
                    return True
        time.sleep(20)
    return False


def delete_chat(cid):
    """DELETE via the cached chat token (chats_http.api is GET-only)."""
    try:
        tok = open(os.path.join(BASE, "flags", "chat_token")).read().strip().strip('"')
        req = urllib.request.Request(
            f"https://chat.z.ai/api/v1/chats/{cid}",
            headers={"Authorization": f"Bearer {tok}"}, method="DELETE")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def ride_to_generation(name, prompt, deadline, tag):
    """Dispatch a WO and ride it to GENERATION; retries until deadline."""
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        wname = f"{name}s-{tag}-{attempt}"
        log(f"dispatching {wname} (attempt {attempt}) via patient path")
        wcid = patient_create(wname, prompt)
        if not wcid:
            log(f"{wname}: create failed/phantom — pacing {WO_PACE_S}s")
            time.sleep(WO_PACE_S)
            continue
        log(f"{wname}: LANDED {wcid[:8]} — riding to generation (watch {GEN_WATCH_S}s)")
        watch_end = time.time() + GEN_WATCH_S
        while time.time() < watch_end and time.time() < deadline:
            time.sleep(30)
            st = chat_state(wcid)
            if st == "GENERATING":
                log(f"PHASE WIN: {wname} ({wcid[:8]}) GENERATING")
                return wcid
            if st in ("reaped", "err"):
                log(f"{wname}: REAPED pre-generation ({st}) — pacing {WO_PACE_S}s")
                break
        else:
            log(f"{wname}: watch budget exhausted without spawn — pacing")
        time.sleep(WO_PACE_S)
    return None


def main():
    t0 = time.time()
    deadline = t0 + MAX_HOURS * 3600
    n = 0
    # run-unique tag: names are NEVER reused across restarts (registry
    # discipline) and create-log tails must never mix runs (a stale abort
    # line from a previous run poisons the failure-pattern match)
    tag = time.strftime("%H%M%S")
    log(f"campaign_sentinel v2 armed: cycle={CYCLE_S}s pace={WO_PACE_S}s "
        f"watch={GEN_WATCH_S}s max={MAX_HOURS}h WOs=[pa018,pa019] tag={tag}")

    for name, prompt in WOS:
        # ---- PROBE: find an admit-window for this WO --------------------
        while time.time() < deadline:
            n += 1
            cname = f"cscanary-{tag}-{n}"
            log(f"probe cycle {n}: patient-dispatching sandbox canary {cname}")
            cid = patient_create(cname, CANARY_PROMPT)
            if not cid:
                log(f"probe cycle {n}: canary create failed/phantom — pacing")
                time.sleep(CYCLE_S)
                continue
            log(f"probe cycle {n}: canary landed {cid[:8]} — waiting for reply")
            if not canary_replied(cid):
                log(f"probe cycle {n}: canary did NOT reply (pool refusing) — pacing")
                time.sleep(CYCLE_S)
                continue
            log(f"probe cycle {n}: CANARY REPLIED — pool ADMITTING; freeing canary chat")
            delete_chat(cid)
            break
        else:
            log("MAX_HOURS reached during probing — TL review needed")
            return 1

        if time.time() >= deadline:
            log("MAX_HOURS reached — TL review needed")
            return 1

        # ---- RIDE: dispatch the WO inside the window --------------------
        wcid = ride_to_generation(name, prompt, deadline, tag)
        if not wcid:
            log(f"MAX_HOURS reached fighting for {name} — TL review needed")
            return 1
        # generation is the reap-safe state; pace before the next WO
        if name != WOS[-1][0]:
            log(f"{name} generating; pacing {WO_PACE_S}s before the next WO "
                f"(serialized launches, lesson 142)")
            time.sleep(WO_PACE_S)

    log("SUCCESS: PA-018 and PA-019 are BOTH GENERATING — sentinel exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
