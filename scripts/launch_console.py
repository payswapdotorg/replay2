#!/usr/bin/env python3
"""launch_console.py — start the PLATFORM console (my-project Next.js app).

2026-09-30 architecture: the replay operator console lives INSIDE the
platform-managed app (/home/z/my-project, src/app/page.tsx + api routes)
so the sandbox preview panel and the console are the SAME server — exactly
one console process family, no port war with the sandbox boot hook.

The ring (supervisor / watcher / custodian) calls this instead of
launch_dev.py when :3000 is dead and no console process exists. It is
equivalent to the platform boot hook: `bun run dev` in /home/z/my-project
(package.json dev script = next dev -p 3000 | tee dev.log, so the canonical
dev.log keeps working).

Env: REPLAY_PORT (default: flags/console_port.txt, then 3000)
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
APP = "/home/z/my-project"

PORT = os.environ.get("REPLAY_PORT", "")
if not PORT:
    # resurrection-proof port config: any spawner without env converges on
    # the file written by deploy.sh
    try:
        PORT = open(os.path.join(FLAGS, "console_port.txt")).read().strip()
    except Exception:
        PORT = "3000"

env = dict(os.environ)
# FORCE (not setdefault): a preset NODE_OPTIONS must not silently drop the cap
env["NODE_OPTIONS"] = "--max-old-space-size=1536"
p = subprocess.Popen(
    ["bun", "run", "dev"],
    stdout=open(os.path.join(BASE, "logs", "console_launch.log"), "a"),
    stderr=subprocess.STDOUT,
    start_new_session=True,
    cwd=APP,
    env=env,
)
# dev.pid stays the ring's tracked handle on the console parent process
try:
    open(os.path.join(FLAGS, "dev.pid"), "w").write(str(p.pid))
except Exception:
    pass
print(f"platform console (my-project) pid {p.pid} (port {PORT})")
