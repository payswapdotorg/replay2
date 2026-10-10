#!/usr/bin/env python3
"""emergency_lane_wrapper.py — keep the emergency driver grinding until done.

The driver halts on milestone failure (exit 5), turn budget (4), or API
abort (3). This wrapper relaunches it (resume mode skips verified
milestones) with a cool-down, forever, until exit 0 (all milestones
verified + bundle captured) or the wrapper is killed.

Usage: emergency_lane_wrapper.py <milestones> <conv-base> <turns-per-ms>
Each relaunch uses a fresh conversation id (conv-base-N) — the driver
history is per-conversation; the REPO STATE carries the real progress.
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = BASE
LOG = os.path.join(ROOT, "logs", "emergency-wrapper.log")
PY = sys.executable
COOLDOWN = 300  # 5 min between driver runs


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main():
    milestones, conv_base, turns = sys.argv[1], sys.argv[2], sys.argv[3]
    attempt = 0
    while True:
        attempt += 1
        conv = "%s-w%d" % (conv_base, attempt)
        log("driver run %d starting (conv %s)" % (attempt, conv))
        r = subprocess.run(
            [PY, os.path.join(BASE, "emergency_lane_driver.py"),
             milestones, conv, turns],
            cwd=ROOT, timeout=6 * 3600)
        code = r.returncode
        log("driver run %d exited %d" % (attempt, code))
        if code == 0:
            log("ALL MILESTONES VERIFIED — wrapper done")
            return 0
        # cooldown then relaunch (resume skips verified milestones)
        log("cooling down %ds before relaunch" % COOLDOWN)
        time.sleep(COOLDOWN)


if __name__ == "__main__":
    main()
