"""launch_replayd.py — start the persistent CDP replay daemon detached.

2026-10-12 recovery #8: the python core now defaults to :3110 — the public
:3100 surface belongs to the bun gateway mini-service (socket.io frames +
/health + /test/drag + legacy endpoint proxying). REPLAYD_PORT still
overrides (replayd.py reads it)."""
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

env = dict(os.environ)
env.setdefault("REPLAYD_PORT", "3110")

p = subprocess.Popen(
    [PY, os.path.join(BASE, "replayd.py")],
    stdout=open(os.path.join(BASE, "logs", "replayd.out"), "a"),
    stderr=subprocess.STDOUT,
    start_new_session=True,
    cwd=BASE,
    env=env,
)
open(os.path.join(BASE, "replayd.pid"), "w").write(str(p.pid))
print("replayd core pid", p.pid, "port", env["REPLAYD_PORT"])
