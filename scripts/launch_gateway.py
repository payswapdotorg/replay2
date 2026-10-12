#!/usr/bin/env python3
"""launch_gateway.py — start the replayd bun gateway mini-service (:3100) detached.

2026-10-12 recovery #8 architecture:
  python replayd core  :3110  (CDP machinery — frames/input/tabs/self-healing)
  bun gateway          :3100  (socket.io live stream + /health + /test/drag +
                               /home test page + legacy endpoint proxying)

The gateway lives at /home/z/my-project/mini-services/replayd (platform
mini-service doctrine: independent bun project, fixed port). This launcher
is what the ring (supervisor/watcher) and deploy.sh call to resurrect it.
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
GATEWAY = "/home/z/my-project/mini-services/replayd"
LOGS = os.path.join(BASE, "logs")
os.makedirs(LOGS, exist_ok=True)

if not os.path.isdir(GATEWAY):
    print(f"gateway dir missing: {GATEWAY}")
    raise SystemExit(1)

# One-time dependency install (no-op when node_modules is present).
if not os.path.isdir(os.path.join(GATEWAY, "node_modules")):
    subprocess.call(["bun", "install"], cwd=GATEWAY,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

p = subprocess.Popen(
    ["bun", "run", "start"],
    stdout=open(os.path.join(LOGS, "gateway.out"), "a"),
    stderr=subprocess.STDOUT,
    start_new_session=True,
    cwd=GATEWAY,
)
open(os.path.join(BASE, "gateway.pid"), "w").write(str(p.pid))
print("replayd gateway pid", p.pid, "port 3100")
