"""launch_monitor.py — start the session-state monitor detached (orphan to
init via immediate-exit launcher, per AGENT_BOOT_PROMPT learning 13)."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

LOG = "/tmp/orbb_sessions.log"

p = subprocess.Popen(
    [PY, os.path.join(BASE, "session_monitor.py")],
    stdout=open("/tmp/session_monitor.err", "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
open("/tmp/session_monitor.pid", "w").write(str(p.pid))
print("monitor pid", p.pid, "->", LOG)
