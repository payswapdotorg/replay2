"""launch_browser_egress.py — start the browser egress probe, detached.

Lesson-13 pattern: Popen(start_new_session=True) from a launcher that EXITS
IMMEDIATELY. Run any time — the probe is single-instance guarded by a
pidfile check.
"""
import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
PIDFILE = os.path.join(BASE, "flags", "browser_egress.pid")


def alive():
    try:
        pid = int(open(PIDFILE).read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


if alive():
    print("browser egress probe already running")
    raise SystemExit(0)

out = open(os.path.join(BASE, "logs", "browser_egress_launch.log"), "a")
p = subprocess.Popen(
    [os.environ.get("PYTHON_BIN", "/home/z/.venv/bin/python3"),
     os.path.join(BASE, "browser_egress_probe.py")],
    stdout=out, stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True)
out.close()
open(PIDFILE, "w").write(str(p.pid))
print(f"browser egress probe pid {p.pid} (detached)")
