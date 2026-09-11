"""launch_create.py — dispatch_worker.py create, fully detached.

Lesson-13 pattern: Popen(start_new_session=True) from a launcher that EXITS
IMMEDIATELY, so the create process reparents to init BEFORE the invoking
tool shell returns. A capacity assault can legally need >10 min; a
tool-shell timeout must never kill it mid-round.

Usage:
  python3 scripts/launch_create.py <session-name> <prompt-file.md>

Output lands in scripts/logs/create_<name>.log; progress is visible via
  python3 scripts/dispatch_worker.py list / check <name>
and the session registry (scripts/flags/session_registry.jsonl).
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(2)

name, prompt_file = sys.argv[1], sys.argv[2]
prompt_file = os.path.abspath(prompt_file)

log_path = os.path.join(BASE, "logs", f"create_{name}.log")
out = open(log_path, "a")
p = subprocess.Popen(
    [os.environ.get("PYTHON_BIN", "/home/z/.venv/bin/python3"),
     os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt_file],
    stdout=out, stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True, cwd=ROOT)
out.close()
print(f"create {name} detached (pid {p.pid}); log: {log_path}")
