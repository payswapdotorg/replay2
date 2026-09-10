import os
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
PY = "/home/z/.venv/bin/python3"
try:
    cand = open(os.path.join(BASE, "python_bin.txt")).read().strip()
    if cand:
        PY = cand
except Exception:
    pass

# launcher pattern (REQUIRED for tool-shell-originated daemons): the bash
# tool kills its own descendants when the session ends — a child re-parented
# to init (via immediate launcher exit) survives. See worklog ring-of-three.
p = subprocess.Popen([PY, os.path.join(BASE, "custodian.py")],
    stdout=open(os.path.join(BASE, "logs", "custodian.log"), "a"),
    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    start_new_session=True, cwd=BASE)
open(os.path.join(BASE, "custodian.pid"), "w").write(str(p.pid))
print("custodian pid", p.pid)
