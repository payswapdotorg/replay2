#!/usr/bin/env python3
"""branch_watch_w10.py — poll Sporta-2.0 remote for wave10 branch deliveries.
Writes a marker file the moment any wave10/worker-* branch appears (or its tip
moves beyond the seen state), so the TL can battery+merge immediately.
Double-fork safe (launched via dfork_launch.py)."""
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "logs", "branch_watch_w10.log")
REPO = "/home/z/sporta-2.0"
BRANCHES = ["wave10/worker-a", "wave10/worker-b", "wave10/worker-c"]
ROUND_S = 150
MAX_ROUNDS = 480  # 20h


def log(msg):
    with open(LOG, "a") as f:
        f.write("[branch-watch-w10 %s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def branch_tip(branch):
    r = subprocess.run(
        ["git", "-C", REPO, "ls-remote", "origin", "refs/heads/" + branch],
        capture_output=True, text=True, timeout=60,
    )
    out = r.stdout.strip()
    return out.split("\t")[0] if out else None


def main():
    log("armed — watching %s every %ss" % (BRANCHES, ROUND_S))
    seen = {}
    for i in range(MAX_ROUNDS):
        for b in BRANCHES:
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
                safe = b.replace("/", "-")
                open(os.path.join(HERE, "flags", "branch-%s.delivery" % safe), "w").write(tip)
                seen[b] = tip
        delivered = len(seen)
        if delivered:
            log("round %d: %d/%d delivered" % (i, delivered, len(BRANCHES)))
        time.sleep(ROUND_S)
    log("MAX_ROUNDS reached — retiring")


if __name__ == "__main__":
    main()
