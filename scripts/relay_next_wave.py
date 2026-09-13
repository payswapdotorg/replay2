#!/usr/bin/env python3
"""relay_next_wave.py — TL relay daemon (2026-09-13).

Serializes the next dispatch wave under the operator's ≤3-concurrent cap:
  w202 fighter (already fighting) lands
    → W204 fighter auto-armed (flag write; supervisor launches poller)
      → w207 fighter auto-armed (flag write)

Each landing = chat live server-side + generation holding 1 of 3 slots. The
relay only arms the NEXT fighter after the previous one LANDS (not merges) —
TL review/merge stays manual (quality gate, never delegated).

Landing detection: the recover flag file disappears (recover_capacity clears
it on rc=0) AND the registry walk-order shows a live sent row for the name.
"""
import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "relay_next_wave.log")
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

WAVE = [
    # (wait-for name, then arm this fighter)
    {"wait_name": "w202-ball-tracking",
     "arm": {"name": "w204-identity-tracking",
             "prompt_file": os.path.join(BASE, "prompts", "s111-w204.md"),
             "flag": "capacity_recover.w204-identity-tracking.json"}},
    {"wait_name": "w204-identity-tracking",
     "arm": {"name": "w207-stt-adapter",
             "prompt_file": os.path.join(BASE, "prompts", "s109-w207.md"),
             "flag": "capacity_recover.w207-stt-adapter.json"}},
]

POLL = 30          # seconds between polls
SETTLE = 90        # seconds after a landing before arming the next fighter
MAX_H = 14         # hard cap: exit and let the TL re-assess


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def flag_path(stem):
    return os.path.join(BASE, "flags", stem)


def fighter_live(name):
    """Registry walk-order: a later void/failed/done invalidates earlier
    creates; a sent row with no later invalidation = live."""
    live = False
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("name") != name:
                    continue
                if r.get("action") in ("void", "failed", "done"):
                    live = False
                elif r.get("sent") and r.get("action") is None:
                    live = True
    except Exception:
        pass
    return live


def landed(name, flag_stem):
    """Landed = fighter flag cleared AND registry shows a live sent row."""
    fp = flag_path(flag_stem)
    if os.path.exists(fp):
        return False
    return fighter_live(name)


def main():
    log("relay armed: w202 -> W204 -> w207 (operator cap 3)")
    t0 = time.time()
    for step in WAVE:
        wait_name = step["wait_name"]
        # the wait-name's own flag stem (name-based)
        wait_stem = f"capacity_recover.{wait_name}.json"
        log(f"waiting for {wait_name} to land (flag {wait_stem}) ...")
        while True:
            if landed(wait_name, wait_stem):
                log(f"{wait_name} LANDED — registry live row confirmed")
                break
            if time.time() - t0 > MAX_H * 3600:
                log(f"relay cap {MAX_H}h hit while waiting on {wait_name} — exiting for TL re-assessment")
                return 3
            time.sleep(POLL)
        time.sleep(SETTLE)
        arm = step["arm"]
        fp = flag_path(arm["flag"])
        if os.path.exists(fp):
            log(f"flag already present for {arm['name']} — supervisor will handle")
        else:
            with open(fp, "w") as f:
                json.dump({"name": arm["name"], "prompt_file": arm["prompt_file"],
                           "uuid": "", "tab_id": ""}, f)
            log(f"ARMED {arm['name']} (flag written; supervisor launches persistent fighter)")
    log("relay complete: w202 + W204 + w207 dispatched wave armed")
    return 0


if __name__ == "__main__":
    sys_rc = main()
    raise SystemExit(sys_rc)
