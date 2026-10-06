#!/usr/bin/env python3
"""branch_watch.py — poll UniCom remote for wave-5 branch deliveries.
Writes a marker file the moment any work/wN-005 branch tip moves beyond
the known-empty state, so the TL can battery+merge immediately.
Double-fork safe (launched via dfork_launch.py)."""
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "logs", "branch_watch.log")
REPO = "/home/z/UniCom"
WAVE = ["w2-006"]
ROUND_S = 120
MAX_ROUNDS = 240  # 8h


def log(msg):
    with open(LOG, "a") as f:
        f.write("[branch-watch %s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def branch_tip(branch):
    r = subprocess.run(
        ["git", "-C", REPO, "ls-remote", "origin", "refs/heads/work/" + branch],
        capture_output=True, text=True, timeout=60,
    )
    out = r.stdout.strip()
    return out.split("\t")[0] if out else None


def main():
    log("armed — watching %s every %ss" % (WAVE, ROUND_S))
    seen = {}
    for i in range(MAX_ROUNDS):
        for b in WAVE:
            try:
                tip = branch_tip(b)
            except Exception as e:
                log("%s: ls-remote error %s" % (b, e))
                continue
            if tip and seen.get(b) != tip:
                if b in seen:
                    log("%s: TIP MOVED %s -> %s" % (b, seen[b][:8], tip[:8]))
                else:
                    log("%s: BRANCH EXISTS @ %s" % (b, tip[:8]))
                open(os.path.join(HERE, "flags", "branch-%s.delivery" % b), "w").write(tip)
                seen[b] = tip
        if len(seen) == len(WAVE):
            # still keep watching for tip movement (workers push often)
            pass
        time.sleep(ROUND_S)
    log("watch window exhausted")


if __name__ == "__main__":
    main()
