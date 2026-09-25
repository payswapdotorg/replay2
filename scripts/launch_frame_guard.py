"""launch_frame_guard.py — start frame_guard.py (:3100 freshness watch) detached.

Lesson-13 pattern (same as launch_replayd.py / launch_create.py): Popen with
start_new_session=True from a launcher that EXITS IMMEDIATELY, so the guard
reparents to init before the invoking tool shell returns. Direct `setsid ... &`
from the tool shell is reaped when the call session ends (observed 2026-09-24:
two frame_guard instances died <60s after direct backgrounding).

Recreated 2026-09-25 after sandbox-reset #4 (lesson-122: the original was
working-copy-only and died with the sandbox — this copy is committed-adjacent;
keep re-committing it to survive resets, or upstream it).

Usage: python3 scripts/launch_frame_guard.py
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)

PY = sys.executable
try:
    cand = open(os.path.join(BASE, "python_bin.txt")).read().strip()
    if cand:
        PY = cand
except Exception:
    pass

p = subprocess.Popen(
    [PY, os.path.join(BASE, "frame_guard.py")],
    stdout=open(os.path.join(BASE, "logs", "frame_guard.out"), "a"),
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    start_new_session=True,
    cwd=BASE,
)
open(os.path.join(BASE, "frame_guard.pid"), "w").write(str(p.pid))
print("frame_guard pid", p.pid)
