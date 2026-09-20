"""launch_backend_probe_watch.py — start backend_probe_watch.py detached."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
p = subprocess.Popen(
    [sys.executable, os.path.join(BASE, "backend_probe_watch.py")],
    stdout=open("/tmp/backend_probe_watch.err", "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
open("/tmp/backend_probe_watch.pid", "w").write(str(p.pid))
print("backend_probe_watch detached pid", p.pid, "-> /tmp/backend_probe_watch.log")
