#!/usr/bin/env python3
"""followup_arm_watch.py — generic dispatched-marker followup (the
prod031_landed_followup.py pattern, parameterized, 2026-09-22).

Watches for flags/<name>-dispatched.marker; on landing:
  1. resolves the chat id from the session registry,
  2. arms waveB_completion_watch.py <name>:<cid> (multi-marker probe),
  3. posts the outbox note.

Usage: followup_arm_watch.py <name> [--every 120] [--max-hours 10]
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
LOG = os.path.join(BASE, "logs", "followup_%s.log")


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("--"):
        print(__doc__)
        return 2
    name = args[0]
    args = args[1:]
    every, max_h = 120, 10
    if "--every" in args:
        i = args.index("--every"); every = int(args[i + 1]); del args[i:i + 2]
    if "--max-hours" in args:
        i = args.index("--max-hours"); max_h = float(args[i + 1]); del args[i:i + 2]
    marker = os.path.join(FLAGS, f"{name}-dispatched.marker")
    logpath = LOG % name

    def log(line):
        stamp = time.strftime("[%H:%M:%S]")
        print(f"{stamp} {line}", flush=True)
        with open(logpath, "a") as f:
            f.write(f"{stamp} {line}\n")

    deadline = time.time() + max_h * 3600
    log(f"watching for {marker} every {every}s")
    while time.time() < deadline:
        if os.path.exists(marker):
            log(f"{name} DISPATCHED marker present — arming completion watch")
            cid = None
            try:
                for line in reversed(open(REGISTRY).read().splitlines()):
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("name") == name and rec.get("url", "").startswith("https://chat.z.ai/c/"):
                        cid = rec["url"].split("/c/")[-1]
                        break
            except FileNotFoundError:
                pass
            if cid:
                os.system(
                    "cd %s && nohup python3 dfork_launch.py "
                    "logs/%s_completion_watch.log python3 waveB_completion_watch.py "
                    "%s:%s --every=150 --max-hours=14 > /dev/null 2>&1 &" % (BASE, name, name, cid)
                )
                log(f"{name} completion watch armed (chat {cid[:8]})")
            else:
                log(f"WARN: {name} chat id not found in registry — the Lead arms the watch next pass")
            rec = {"ts": int(time.time() * 1000), "text":
                   f"{name.upper()} DISPATCHED — completion watch armed (multi-marker probe)."}
            with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
                f.write(json.dumps(rec) + "\n")
            return 0
        time.sleep(every)
    log(f"burnout: {name} never landed within max-hours")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
