"""launch_resident.py — start the resident agent presence, detached.

Lesson-13 pattern: Popen(start_new_session=True) from a launcher that EXITS
IMMEDIATELY, so the child reparents to init BEFORE the invoking shell call
returns. A tool-shell timeout (or the shell reaping its descendant tree)
must never kill the resident. Run me any time — the resident is
flock-guarded, so a second launch while one is alive is a no-op.
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))

out = open(os.path.join(BASE, "logs", "resident_launch.log"), "a")
p = subprocess.Popen([os.environ.get("PYTHON_BIN", "/home/z/.venv/bin/python3"),
                      os.path.join(BASE, "resident_agent.py")],
                     stdout=out, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True)
out.close()
print(f"resident agent pid {p.pid} (detached)")
