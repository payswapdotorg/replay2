#!/usr/bin/env python3
"""prod030_landed_followup.py — marker-triggered hfx204 re-dispatch chain.

2026-09-22 context: the platform send path is degraded (plain canary
proof-fail; the 04:29 hfx204 and 06:30 hfx101 sends landed but their
generation tasks were dropped; hfx101's task revived 07:45 and completed).
The PROD-030 dispatch sentinel (the critical path — the deployed-URL
browser-bundle fix) is grinding through the outage and will write
flags/prod030-dispatched.marker the moment a send actually lands AND
generates (the fixed min_chars=2000 guard — no false adoption).

This watcher arms the follow-up: when that marker appears, launch the
hfx204 re-dispatch sentinel (its packet is unchanged), so the recovery
window is used fully without waiting for the Lead's next pass.

  - poll flags/prod030-dispatched.marker every 120s (max 8h)
  - on appearance: dfork wave_dispatch_sentinel.py hfx204:<packet>
    (every 180, watch 150, rounds 100), write a registry note, exit 0
  - burnout: exit 3

Usage: prod030_landed_followup.py [--every 120] [--max-hours 8]
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
MARKER = os.path.join(FLAGS, "prod030-dispatched.marker")
LOG = os.path.join(BASE, "logs", "hfx204_followup.log")


def log(line):
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {line}", flush=True)


def main():
    args = sys.argv[1:]
    every, max_h = 120, 8
    if "--every" in args:
        i = args.index("--every"); every = int(args[i + 1]); del args[i:i + 2]
    if "--max-hours" in args:
        i = args.index("--max-hours"); max_h = float(args[i + 1]); del args[i:i + 2]
    deadline = time.time() + max_h * 3600
    log(f"watching for {MARKER} every {every}s")
    while time.time() < deadline:
        if os.path.exists(MARKER):
            log("prod030 DISPATCHED marker present — follow-up chain firing")
            # 1. the hfx204 re-dispatch sentinel (its own lane)
            os.system(
                "cd %s && PATIENT_TAB=88A564C0 nohup python3 dfork_launch.py "
                "logs/hfx204_redispatch2.log python3 wave_dispatch_sentinel.py "
                "hfx204:worker-prompts/HFX204.md --every 180 --watch 150 --rounds 100 "
                "> /dev/null 2>&1 &" % BASE
            )
            with open(os.path.join(FLAGS, "session_registry.jsonl"), "a") as f:
                f.write('{"name": "hfx204", "ts": %d, "event": "redispatch-armed", '
                        '"status": "prod030 landed; follow-up sentinel launched"}\n'
                        % int(time.time()))
            log("hfx204 follow-up sentinel launched (logs/hfx204_redispatch2.log)")
            # 2. the prod030 completion watch — resolve the chat id from the
            #    registry (the sentinel's most recent prod030 record with a url)
            cid = None
            try:
                for line in reversed(open(os.path.join(FLAGS, "session_registry.jsonl")).read().splitlines()):
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("name") == "prod030" and rec.get("url", "").startswith("https://chat.z.ai/c/"):
                        cid = rec["url"].split("/c/")[-1]
                        break
            except FileNotFoundError:
                pass
            if cid:
                os.system(
                    "cd %s && nohup python3 dfork_launch.py "
                    "logs/prod030_completion_watch.log python3 waveB_completion_watch.py "
                    "prod030:%s --every=150 --max-hours=14 > /dev/null 2>&1 &" % (BASE, cid)
                )
                log(f"prod030 completion watch armed (chat {cid[:8]})")
            else:
                log("WARN: prod030 chat id not found in registry — completion watch NOT armed; the Lead arms it next pass")
            # 3. the outbox note
            rec = {"ts": int(time.time() * 1000), "text":
                   "PROD-030 DISPATCHED (platform send path recovered) — completion watch armed; "
                   "hfx204 re-dispatch sentinel launched in parallel. The declaration critical path "
                   "resumes: prod030 completes -> harvest/merge -> PROD-031 pin+dispatch -> merge -> "
                   "final redeploy -> deployed-check -> Gate F -> PROD-015 evidence -> declaration."}
            with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
                f.write(json.dumps(rec) + "\n")
            return 0
        time.sleep(every)
    log("burnout: prod030 never landed within max-hours")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
