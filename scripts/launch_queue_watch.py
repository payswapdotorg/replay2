"""launch_queue_watch.py — start a detached queue_watch.py for one session
(orphan to init via immediate-exit launcher, per learning 13).

Usage: launch_queue_watch.py <name> <tab-prefix> [marker]
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

if len(sys.argv) < 3:
    print("usage: launch_queue_watch.py <name> <tab-prefix> [marker]")
    sys.exit(1)

name, tab_prefix = sys.argv[1], sys.argv[2]
marker = sys.argv[3] if len(sys.argv) > 3 else "FINAL REPORT"

p = subprocess.Popen(
    [PY, os.path.join(BASE, "queue_watch.py"), name, tab_prefix, marker],
    stdout=open(f"/tmp/queue_watch_{name}.log", "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
print(f"queue_watch[{name}] detached pid {p.pid} -> /tmp/queue_watch_{name}.log")
