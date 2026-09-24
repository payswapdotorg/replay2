#!/usr/bin/env python3
"""launch_patient.py — patient_dispatch.py, fully detached (lesson-13).

RECREATED 2026-09-24 during sandbox-reset recovery: the original launcher
was working-copy-only and died with the sandbox (lesson-122 violation —
this copy is committed to the repo so the next reset cannot lose it).

Concurrent-wave pin doctrine (2026-09-21/24): opens a FRESH chat.z.ai home
tab and pins the dispatch to it via PATIENT_TAB — patient_dispatch
navigates its tab to home for the New Task surface, so it must never be
pointed at a live worker-chat tab. One dispatch = one dedicated tab.

Usage: python3 launch_patient.py <session-name> <prompt-file.md>
Output: scripts/logs/create_<name>.log  (the auto_pipeline CREATE_LOG contract —
        the 2026-09-24 reset recreation first wrote patient_<name>.log and the
        pipeline's create_verdict read no-log; path now matches the contract)
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(2)

name, prompt_file = sys.argv[1], os.path.abspath(sys.argv[2])
log_path = os.path.join(BASE, "logs", f"create_{name}.log")

# Fresh home tab, pinned — never reuse a tab another dispatch or worker
# chat occupies (interleaved DOM operations would corrupt both).
pin = ""
try:
    tab = channel.new_tab("https://chat.z.ai/")
    pin = (tab.get("id") or "")[:8]
except Exception as e:
    print(f"WARN: fresh-tab open failed ({e}) — launching unpinned "
          "(safe only when no other dispatch is running)")

env = dict(os.environ)
if pin:
    env["PATIENT_TAB"] = pin

p = subprocess.Popen(
    [os.environ.get("PYTHON_BIN", "/home/z/.venv/bin/python3"),
     os.path.join(BASE, "patient_dispatch.py"), name, prompt_file],
    stdout=open(log_path, "a"), stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True,
    cwd=os.path.dirname(BASE), env=env)
print(f"patient dispatch {name} detached (pid {p.pid}, pin {pin or '-'}); "
      f"log: {log_path}")
