#!/usr/bin/env python3
"""launch_daemon.py <logname> <cmd> [args...] — fully-detached daemon launch
(the launch_patient.py detachment contract: Popen(start_new_session=True)
from a launcher that exits immediately, so the daemon survives the invoking
tool shell's process-tree reaping)."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

logname, cmd = sys.argv[1], sys.argv[2:]
log_path = os.path.join(BASE, "logs", logname)
out = open(log_path, "a")
env = dict(os.environ)
p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, start_new_session=True,
                     cwd=BASE, env=env)
out.close()
print(f"daemon detached (pid {p.pid}); log: {log_path}")
