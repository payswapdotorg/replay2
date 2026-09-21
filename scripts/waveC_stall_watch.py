#!/usr/bin/env python3
"""waveC_stall_watch.py — generation-stall monitor for Wave C (2026-09-21).

Context: platform-wide generation stall diagnosed at ~15:35 UTC (both GLM-5.2
plain probe and GLM-5.3 staged workers show zero batch messages; messages land
server-side; pods Running). The two staged worker chats hold their packets and
can fire late when generation resumes.

Watches three things every 180s:
  1. CANARY (a plain glm-5.2 chat with a trivial ask) — a reply means
     generation has resumed platform-wide.
  2. The two staged worker chats — generation start (batch msgs > 0) or
     REAP (chat gone from the batch probe) — a reap means the packet is lost
     and the Lead must re-dispatch.
  3. Posts an outbox alert on every state TRANSITION (not every poll).

Passive: no dispatch power, no tab manipulation.
Usage: waveC_stall_watch.py --every=180 --max-hours=12
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")

CANARY = "3b8cebf6-7740-4971-9159-cd99ef795e08"
WORKERS = {
    "prod025": "adbb8683-463c-42be-bd26-a24381776c60",
    "prod024": "a33b7555-e27b-411c-bdab-6f751d487ced",
}


def log(line):
    print(time.strftime("[%H:%M:%S]") + f" [stall-watch] {line}", flush=True)


def post_outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception as e:
        log(f"outbox write failed: {e}")


def probe(cid):
    """Returns (state, detail) — state in {reaped, staged, generating, error}."""
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(BASE, "batch_probe.py"), cid, "ZZZ-NO-MARKER"],
            capture_output=True, text=True, timeout=120)
        txt = out.stdout.strip() or out.stderr.strip()
        if '"err"' in txt or not txt:
            return "error", txt[:80]
        d = json.loads(txt)
        msgs = d.get("batch", {}).get("msgs", 0)
        if msgs == 0:
            return "staged", "0 msgs"
        return "generating", f"{msgs} msgs"
    except Exception as e:
        return "error", str(e)[:80]


def main():
    every, max_h = 180, 12
    for a in sys.argv[1:]:
        if a.startswith("--every="):
            every = int(a.split("=", 1)[1])
        elif a.startswith("--max-hours="):
            max_h = int(a.split("=", 1)[1])
    state = {"canary": "staged", "prod025": "staged", "prod024": "staged"}
    log(f"watching canary + {sorted(WORKERS)}; every={every}s max={max_h}h")
    t0 = time.time()
    while time.time() - t0 < max_h * 3600:
        time.sleep(every)
        # canary first — its transition matters most for posture
        targets = [("canary", CANARY)] + sorted(WORKERS.items())
        for name, cid in targets:
            s, detail = probe(cid)
            if s == "error":
                # a reap looks like an API error (404/500 on a gone chat);
                # distinguish: re-probe once after a pause
                time.sleep(20)
                s2, d2 = probe(cid)
                if s2 == "error":
                    s, detail = "reaped?", d2
            if s != state[name]:
                old = state[name]
                state[name] = s
                log(f"{name}: {old} -> {s} ({detail})")
                if name == "canary" and s == "generating":
                    post_outbox("GENERATION RESUMED (canary replied) — platform stall is over; "
                                "the staged Wave C workers should fire or be re-checked now.")
                elif s == "generating":
                    post_outbox(f"{name.upper()} is GENERATING — the stall lifted and the worker started.")
                elif "reaped" in s:
                    post_outbox(f"{name.upper()} looks REAPED ({detail}) — the staged packet is lost; "
                                "the Lead must re-dispatch that work item.")
        if all(v == "generating" for v in state.values()):
            log("everything generating — stall-watch mission complete")
            return 0
    log(f"timeout after {max_h}h; final state: {state}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
