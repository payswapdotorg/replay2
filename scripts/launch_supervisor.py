#!/usr/bin/env python3
"""launch_supervisor.py — start the resident supervisor detached.

dfork pattern (2026-09-28 reaper lesson, restated 2026-09-30): processes
spawned directly by an agent CLI session are reaped when that session's
Bash call ends; only GRANDchildren (this script's Popen with
start_new_session=True) survive. deploy.sh uses the same shape via its
inline `setsid nohup ... &` inside the script — this launcher makes the
same escape available for manual/TL restarts so a relaunched supervisor
does not silently vanish one tool-call later.
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

PY = sys.executable
try:
    cand = open(os.path.join(BASE, "python_bin.txt")).read().strip()
    if cand:
        PY = cand
except Exception:
    pass

p = subprocess.Popen(
    [PY, os.path.join(BASE, "supervisor.py")],
    stdout=open(os.path.join(BASE, "logs", "supervisor.log"), "a"),
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    start_new_session=True,
    cwd=BASE,
)
open(os.path.join(BASE, "supervisor.pid"), "w").write(str(p.pid))
print(f"supervisor pid {p.pid} (dfork-detached)")
