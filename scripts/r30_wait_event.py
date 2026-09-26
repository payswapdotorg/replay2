#!/usr/bin/env python3
"""r30_wait_event.py — block until the R30-B pipeline state CHANGES (lead loop).

Polls every 20s (local files + process checks only — no platform traffic):
- flags/r30b-chat-id appears      -> exit 10 (DISPATCHED)
- flags/r30b-complete appears     -> exit 20 (worker COMPLETE)
- flags/r30b-dead appears         -> exit 30 (worker DEAD)
- the quiet-hold log gains a new cycle-outcome line -> exit 5 (cycle outcome)
- the quiet-hold daemon dies (unexpected)           -> exit 40
- 9.5 min pass with no change                      -> exit 0 (timeout, keep looping)
"""
import os
import subprocess
import sys
import time

BASE = "/home/z/replay2/scripts"
FLAGS = f"{BASE}/flags"
QUIET_LOG = f"{BASE}/logs/r30b-assault.log"
WATCH_LOG = f"{BASE}/logs/r30b-watch.log"
POLL_S = 20
MAX_S = 570


def log_lines(path):
    try:
        return len(open(path).read().splitlines())
    except FileNotFoundError:
        return 0


def outcome_count(path):
    try:
        return sum(1 for l in open(path)
                   if "failed; holding" in l or "SUCCESS" in l
                   or "EXHAUSTED" in l)
    except FileNotFoundError:
        return 0


def daemon_alive():
    p = subprocess.run(["pgrep", "-f", "r30b_assault"],
                       capture_output=True, text=True)
    return bool(p.stdout.strip())


def main():
    t0 = time.time()
    base_outcomes = outcome_count(QUIET_LOG)
    base_watch = log_lines(WATCH_LOG)
    had_chat_id = os.path.isfile(f"{FLAGS}/r30b-chat-id")
    while time.time() - t0 < MAX_S:
        if os.path.isfile(f"{FLAGS}/r30b-complete"):
            print("EVENT: worker COMPLETE")
            return 20
        if os.path.isfile(f"{FLAGS}/r30b-dead"):
            print("EVENT: worker DEAD")
            return 30
        now_chat_id = os.path.isfile(f"{FLAGS}/r30b-chat-id")
        if now_chat_id and not had_chat_id:
            print("EVENT: DISPATCHED (chat-id pinned)")
            return 10
        if not daemon_alive():
            print("EVENT: quiet daemon died unexpectedly")
            return 40
        if outcome_count(QUIET_LOG) > base_outcomes:
            print("EVENT: new cycle outcome in quiet-hold log")
            return 5
        if log_lines(WATCH_LOG) > base_watch:
            print("EVENT: watcher log activity (worker live?)")
            return 15
        time.sleep(POLL_S)
    print("no change (timeout)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
