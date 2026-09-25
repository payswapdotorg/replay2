"""launch_server_watch.py — server_watch.py, fully detached (lesson-13 pattern).

Usage: python3 scripts/launch_server_watch.py [window-hours]
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

hours = sys.argv[1] if len(sys.argv) > 1 else "8"
out = open(os.path.join(BASE, "logs", "server_watch_launch.log"), "a")
p = subprocess.Popen(
    ["/home/z/.venv/bin/python3", "-u", os.path.join(BASE, "server_watch.py"), hours],
    stdout=out, stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True, cwd=BASE)
out.close()
print(f"server_watch detached (pid {p.pid})")
