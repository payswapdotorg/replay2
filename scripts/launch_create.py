"""launch_create.py — start a detached dispatch_worker create (orphan to
init via immediate-exit launcher, per AGENT_BOOT_PROMPT learning 13).

Usage: launch_create.py <name> <prompt_file> [timeout_secs]
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

if len(sys.argv) < 3:
    print("usage: launch_create.py <name> <prompt_file> [timeout_secs]")
    sys.exit(1)

name, prompt_file = sys.argv[1], sys.argv[2]
budget = sys.argv[3] if len(sys.argv) > 3 else "2700"
log = f"/tmp/create_{name}.log"

p = subprocess.Popen(
    ["timeout", budget, PY, os.path.join(BASE, "dispatch_worker.py"),
     "create", name, os.path.abspath(prompt_file)],
    stdout=open(log, "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
open(f"/tmp/create_{name}.pid", "w").write(str(p.pid))
print(f"create {name} detached pid {p.pid} -> {log}")
