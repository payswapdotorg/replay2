"""launch_prod.py — start the PRODUCTION console (next start, default :3000).

TL 2026-10-17... no — 2026-10-09: dev-mode RSS grew ~130MB/min under UI frame
polling (external buffer memory; the 1024MB V8 old-space cap can't see it) and
OOM-killed the console at 15:59Z and ~17:07Z. The production server holds flat
memory. Serves from .next-prod (NEXT_DIST_DIR) — build with:

    NEXT_DIST_DIR=.next-prod bun run build

Env: REPLAY_PORT (default from flags/console_port.txt, else 3000)
Falls back cleanly: if this server ever dies, the supervisor's ensure_dev
relaunches DEV mode on :3000 (leaky but functional) — the watchdog chain
never leaves the operator without a console.
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
PORT = os.environ.get("REPLAY_PORT", "")
if not PORT:
    # resurrection-proof port config: any spawner without env converges on
    # the file written by deploy.sh (same doctrine as launch_dev.py)
    try:
        PORT = open(os.path.join(BASE, "flags", "console_port.txt")).read().strip()
    except Exception:
        PORT = "3000"

# 2026-10-09 guard: never leave the operator without a console. If the prod
# bundle is missing (fresh clone / failed build), delegate to DEV mode —
# leaky but functional (the supervisor's ensure_dev doctrine, extended to
# the prod path so a resurrection can never dead-end).
if not os.path.exists(os.path.join(ROOT, ".next-prod", "BUILD_ID")):
    print("launch_prod: .next-prod/BUILD_ID missing — delegating to launch_dev.py")
    import runpy
    runpy.run_path(os.path.join(BASE, "launch_dev.py"), run_name="__main__")
    raise SystemExit(0)

env = dict(os.environ)
# Env parity with the dev deployment: deploy.sh sources scripts/env.sh (+
# ~/.secrets/env.sh) before launching the stack, so the dev server inherits
# REPO, OPERATOR_PAT, COMPOSIO_*, E2B_API_KEY... A launcher that skips this
# breaks the console repo card (bridge.py's file-parse regex can't match
# quoted values — see the 2026-10-09 quote fix) and the agent chat's
# remote_bash/web tools (E2B key). Source the same files here.
import subprocess as _sp
try:
    out = _sp.run(
        ["bash", "-c",
         'source "%s" 2>/dev/null; source "$HOME/.secrets/env.sh" 2>/dev/null; '
         'env' % os.path.join(BASE, "env.sh")],
        capture_output=True, text=True, timeout=10).stdout
    for line in out.splitlines():
        if "=" in line and not line.startswith("_="):
            k, _, v = line.partition("=")
            if k and k.isupper() or k in ("PATH", "HOME"):
                env[k] = v
except Exception:
    pass
# Keep the same 1024MB old-space cap (belt + braces; prod RSS stays ~300MB).
env["NODE_OPTIONS"] = "--max-old-space-size=1024"
env["NEXT_DIST_DIR"] = ".next-prod"

p = subprocess.Popen(["bun", "run", "start", "--", "-p", PORT],
    stdout=open(os.path.join(BASE, "logs", "prod.log"), "ab"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=ROOT, env=env)
open(os.path.join(BASE, "flags", "prod.pid"), "w").write(str(p.pid))
print(f"prod console pid {p.pid} (port {PORT}, .next-prod)")
