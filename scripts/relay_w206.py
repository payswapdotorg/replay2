#!/usr/bin/env python3
"""relay_w206.py — arm the W206 fighter after the NEXT landing among
(w207-stt-adapter, w205-ball-state). Keeps at most TWO create assaults
running concurrently (Chrome strain lesson 89b/14:28 incident); the third
(W206) fires the moment one of the two current fighters lands.
"""
import json
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "relay_next_wave.log")
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

WAIT_SET = ["w207-stt-adapter", "w205-ball-state"]
ARM_FLAG = os.path.join(BASE, "flags", "capacity_recover.w206-fusion.json")
ARM_SPEC = {"name": "w206-fusion", "prompt_file": os.path.join(BASE, "prompts", "s113-w206.md"),
            "uuid": "", "tab_id": ""}
POLL = 30
MAX_H = 14


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def fighter_live(name):
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


def main():
    log("relay w206 armed: waiting for a landing among w207/w205 ...")
    t0 = time.time()
    while True:
        for name in WAIT_SET:
            if fighter_live(name):
                log(f"{name} landed — arming W206 fighter now")
                with open(ARM_FLAG, "w") as f:
                    json.dump(ARM_SPEC, f)
                log("W206 flag written; supervisor launches persistent fighter")
                return 0
        if time.time() - t0 > MAX_H * 3600:
            log("relay w206 cap hit — exiting for TL re-assessment")
            return 3
        time.sleep(POLL)


if __name__ == "__main__":
    raise SystemExit(main())
