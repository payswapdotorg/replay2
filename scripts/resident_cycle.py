#!/usr/bin/env python3
"""resident_cycle.py — one resident-watch cycle status: lanes, markers, frontier.
Exit codes: 0 = all quiet; 3 = completion marker present (action needed)."""
import glob, json, os, re, subprocess, sys, time

F = "/home/z/replay2/scripts/flags"
LANES = ["T030", "T031", "T043"]
LOGS = {"T030": "/tmp/queue_watch_T030.log",
        "T031": "/tmp/queue_watch_T031.log",
        "T043": "/tmp/queue_watch_T043.log"}

action = False
print("=== %s UTC ===" % time.strftime("%H:%M:%S"))
for n in LANES:
    mk = os.path.join(F, "%s-complete.marker" % n)
    if os.path.exists(mk):
        print("%s: *** COMPLETE MARKER PRESENT ***" % n)
        action = True
        continue
    try:
        last = open(LOGS[n]).read().strip().splitlines()[-1]
    except Exception:
        last = "(no log)"
    m = re.search(r"\] (\S+) (chars=\d+)(?: hits=(\d+))?", last)
    state = m.group(1) if m else last[:60]
    # alive watcher?
    alive = subprocess.run(["pgrep", "-f", "queue_watch.py %s " % n],
                           capture_output=True).returncode == 0
    print("%s: %-16s watcher=%s" % (n, state, "alive" if alive else "DEAD"))
    if not alive:
        action = True

# marker files may also appear for future waves
extra = [p for p in glob.glob(os.path.join(F, "*-complete.marker"))
         if os.path.basename(p).split("-")[0] not in LANES]
for p in extra:
    print("EXTRA MARKER: %s" % p)
    action = True

sys.exit(3 if action else 0)
