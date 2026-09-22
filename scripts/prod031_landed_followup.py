#!/usr/bin/env python3
"""prod031_landed_followup.py — arm the prod031 completion watch when the
dispatch marker appears (the prod030_landed_followup.py pattern, 2026-09-22).

The dispatch sentinel (wave_dispatch_sentinel.py, PATIENT_TAB=2CA674B1...) may
land the packet at any hour of the platform capacity grind. This watcher
closes the loop without a Lead pass:

  on flags/prod031-dispatched.marker:
    1. resolve the prod031 chat id from the session registry (last record
       with a chat.z.ai/c/ url),
    2. arm waveB_completion_watch.py prod031:<cid> (multi-marker probe —
       the translated-headline doctrine),
    3. post the outbox note.

Usage: prod031_landed_followup.py [--every 120] [--max-hours 10]
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
MARKER = os.path.join(FLAGS, "prod031-dispatched.marker")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
LOG = os.path.join(BASE, "logs", "prod031_followup.log")


def log(line):
    stamp = time.strftime("[%H:%M:%S]")
    print(f"{stamp} {line}", flush=True)
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def main():
    args = sys.argv[1:]
    every, max_h = 120, 10
    if "--every" in args:
        i = args.index("--every"); every = int(args[i + 1]); del args[i:i + 2]
    if "--max-hours" in args:
        i = args.index("--max-hours"); max_h = float(args[i + 1]); del args[i:i + 2]
    deadline = time.time() + max_h * 3600
    log(f"watching for {MARKER} every {every}s")
    while time.time() < deadline:
        if os.path.exists(MARKER):
            log("prod031 DISPATCHED marker present — arming completion watch")
            cid = None
            try:
                for line in reversed(open(REGISTRY).read().splitlines()):
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("name") == "prod031" and rec.get("url", "").startswith("https://chat.z.ai/c/"):
                        cid = rec["url"].split("/c/")[-1]
                        break
            except FileNotFoundError:
                pass
            if cid:
                os.system(
                    "cd %s && nohup python3 dfork_launch.py "
                    "logs/prod031_completion_watch.log python3 waveB_completion_watch.py "
                    "prod031:%s --every=150 --max-hours=14 > /dev/null 2>&1 &" % (BASE, cid)
                )
                log(f"prod031 completion watch armed (chat {cid[:8]})")
            else:
                log("WARN: prod031 chat id not found in registry — the Lead arms the watch next pass")
            rec = {"ts": int(time.time() * 1000), "text":
                   "PROD-031 DISPATCHED — completion watch armed (multi-marker probe). "
                   "The declaration critical path: prod031 completes -> harvest/merge/push -> "
                   "final redeploy (quota sentinel already grinding) -> deployed-check -> "
                   "Gate F both journeys -> PROD-015 evidence packet -> audit -> declaration."}
            with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
                f.write(json.dumps(rec) + "\n")
            return 0
        time.sleep(every)
    log("burnout: prod031 never landed within max-hours")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
