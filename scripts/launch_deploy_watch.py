#!/usr/bin/env python3
"""launch_deploy_watch.py — start deploy_watch.py detached the PROVEN way
(subprocess.Popen + start_new_session=True, exactly the rearm_lanes.py
remote_watch mechanism that survives the sandbox's background reaper)."""
import os
import subprocess
import sys

BASE = "/home/z/replay2/scripts"
LOGDIR = os.path.join(BASE, "logs")
os.makedirs(LOGDIR, exist_ok=True)

def resident_pids():
    """PIDs running deploy_watch.py EXACTLY (never the launcher itself —
    the naive pgrep -f 'deploy_watch.py' self-matches 'launch_deploy_watch.py')."""
    r = subprocess.run(["pgrep", "-f", "deploy_watch"], capture_output=True, text=True)
    pids = []
    for pid in (p for p in r.stdout.split() if p.isdigit()):
        try:
            cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
        except OSError:
            continue
        argv = cmd.split("\0")
        if argv and argv[0] and any(a.rstrip() == "deploy_watch.py" for a in argv if a):
            pids.append(pid)
    return pids


found = resident_pids()
if found:
    print("deploy_watch already resident:", " ".join(found))
    sys.exit(0)

p = subprocess.Popen(
    ["/home/z/.venv/bin/python3", os.path.join(BASE, "deploy_watch.py")],
    stdout=open(os.path.join(LOGDIR, "deploy_watch.stderr.log"), "a"),
    stderr=subprocess.STDOUT,
    start_new_session=True,
    cwd=BASE,
)
print(f"deploy_watch detached pid {p.pid} -> logs/deploy_watch.stderr.log")
