"""launch_dev.py — start the Next.js console (default :3000).

Heap cap: next-server can balloon and get OOM-killed, taking the stack down.
Capping V8 old-space keeps the dev server bounded; the supervisor/watchdog
pair handles the rare restart if it hits the cap.

Env: REPLAY_PORT (default 3000)
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
PORT = os.environ.get("REPLAY_PORT", "")
if not PORT:
    # resurrection-proof port config: any spawner without env (supervisor,
    # watcher, custodian) converges on the file written by deploy.sh.
    try:
        PORT = open(os.path.join(BASE, "flags", "console_port.txt")).read().strip()
    except Exception:
        PORT = "3000"

env = dict(os.environ)
# 1024MB V8 old-space (agent-chat load measured ~1.3-1.4GB RSS worst case on
# the 4GB box). FORCE-set: setdefault silently drops the cap if NODE_OPTIONS
# is preset (wave-3 lesson).
env["NODE_OPTIONS"] = "--max-old-space-size=1024"
p = subprocess.Popen(["bun", "run", "dev", "--", "-p", PORT],
    stdout=open(os.path.join(BASE, "dev.log"), "w"), stderr=subprocess.STDOUT,
    start_new_session=True, cwd=ROOT, env=env)
open(os.path.join(BASE, "dev.pid"), "w").write(str(p.pid))
print(f"dev server pid {p.pid} (port {PORT})")
