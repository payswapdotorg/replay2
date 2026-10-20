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
# Resurrection-proof deployment secrets (2026-10-20): deploy.sh sources
# scripts/env.sh so its own console start inherits the deployment secrets —
# but the supervisor/watcher resurrect paths spawn this script with a bare
# env, which silently dropped the self-hosted model backend config (the
# drought lane) on every auto-restart. Source the deployment-local env here
# so ANY spawner yields a console with the same secrets deploy.sh provides.
# Only sets keys the spawner did not already provide (explicit env wins).
_env_sh = os.path.join(BASE, "env.sh")
if os.path.isfile(_env_sh):
    try:
        with open(_env_sh) as f:
            for _line in f:
                _line = _line.strip()
                if _line.startswith("export ") and "=" in _line:
                    _k, _, _v = _line[len("export "):].partition("=")
                    _k = _k.strip()
                    _v = _v.strip().strip('"').strip("'")
                    if _k and _k not in env:
                        env[_k] = _v
    except Exception:
        pass
# 1024MB V8 old-space (agent-chat load measured ~1.3-1.4GB RSS worst case on
# the 4GB box). FORCE-set: setdefault silently drops the cap if NODE_OPTIONS
# is preset (wave-3 lesson).
env["NODE_OPTIONS"] = "--max-old-space-size=1024"
p = subprocess.Popen(["bun", "run", "dev", "--", "-p", PORT],
    stdout=open(os.path.join(BASE, "dev.log"), "w"), stderr=subprocess.STDOUT,
    start_new_session=True, cwd=ROOT, env=env)
open(os.path.join(BASE, "dev.pid"), "w").write(str(p.pid))
print(f"dev server pid {p.pid} (port {PORT})")
