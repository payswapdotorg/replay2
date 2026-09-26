#!/usr/bin/env python3
"""branch_watch.py — ls-remote poller for in-flight worker branches.

Polls the repo for the given branch names every POLL_S; when a branch
appears (or its sha advances), records it and notifies the console thread.
The TL harvests on chat completion markers; this catches the git delivery
even between TL check-ins.

Usage (lesson-147 orphan idiom):
  bash -c 'cd /home/z/replay2/scripts && setsid nohup python3 \
      branch_watch.py <tag> <branch1> <branch2> [...] \
      < /dev/null > logs/branch_watch_<tag>.log 2>&1 &'
"""
import os
import re
import subprocess
import sys
import time

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
REPO = "https://github.com/payswapdotorg/RoamLink.git"
POLL_S = 150
MAX_HOURS = float(os.environ.get("MAX_HOURS", "8"))


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def outbox(text):
    try:
        import json
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "text": text}) + "\n")
    except Exception as e:  # noqa: BLE001
        log("outbox write failed: %s" % e)


def ls_remote_branch(branch):
    """Returns the sha of the branch, or None. git ls-remote is not
    API-rate-limited (the standing workaround for exhausted api.github.com)."""
    try:
        p = subprocess.run(["git", "ls-remote", REPO, branch],
                           capture_output=True, text=True, timeout=60)
        m = re.search(r"^([0-9a-f]{40})\s+refs/heads/" + re.escape(branch) + r"$",
                      p.stdout.strip(), re.M)
        return m.group(1) if m else None
    except Exception as e:  # noqa: BLE001
        log("ls-remote failed: %s" % e)
        return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    tag = sys.argv[1]
    branches = sys.argv[2:]
    log("branch_watch armed: tag=%s branches=%s poll=%ds max=%.1fh"
        % (tag, branches, POLL_S, MAX_HOURS))
    seen = {b: None for b in branches}
    notified = {b: False for b in branches}
    deadline = time.time() + MAX_HOURS * 3600
    while time.time() < deadline:
        time.sleep(POLL_S)
        for b in branches:
            sha = ls_remote_branch(b)
            if sha is None:
                continue
            if seen[b] is None:
                seen[b] = sha
                if not notified[b]:
                    notified[b] = True
                    log("BRANCH PUSHED: %s @ %s" % (b, sha[:10]))
                    outbox("BRANCH WATCH: %s pushed @ %s — the worker's git "
                           "delivery landed; TL harvest/gate follows the "
                           "chat completion marker." % (b, sha[:10]))
            elif sha != seen[b]:
                log("BRANCH ADVANCED: %s %s -> %s" % (b, seen[b][:10], sha[:10]))
                seen[b] = sha
    log("MAX_HOURS reached — exiting")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
