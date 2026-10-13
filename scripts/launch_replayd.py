"""launch_replayd.py — start the persistent CDP replay daemon detached.

2026-10-12 recovery #8: the python core now defaults to :3110 — the public
:3100 surface belongs to the bun gateway mini-service (socket.io frames +
/health + /test/drag + legacy endpoint proxying).

2026-10-13 churn fix ("always fix the replay"): deploy.sh exports
REPLAYD_PORT=3100 (the GATEWAY's public port) into the whole supervised
tree; the old env.setdefault("REPLAYD_PORT", "3110") inherited that value,
so a supervisor core-restart bound the core onto :3100 — colliding with the
gateway (OSError 98 EADDRINUSE death-loop, observed 2026-10-13 08:22Z).
The core's port authority is now REPLAYD_CORE_PORT (default 3110); a raw
REPLAYD_PORT in the environment is treated as gateway pollution and
overridden. replayd.py still reads REPLAYD_PORT — the launcher sets it
from the core-port authority."""
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
# 2026-10-13 churn fix: REPLAYD_CORE_PORT is the core's port authority
# (default 3110). A raw REPLAYD_PORT in the environment is deploy.sh's
# gateway-public-port export — pollution for the core; override it.
env["REPLAYD_PORT"] = env.get("REPLAYD_CORE_PORT") or "3110"

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
