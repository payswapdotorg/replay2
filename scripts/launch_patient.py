"""launch_patient.py — patient_dispatch.py, fully detached (lesson-13 pattern).

Same detachment contract as launch_create.py: Popen(start_new_session=True)
from a launcher that exits immediately, so the patient dispatch survives the
invoking tool shell. Honors PATIENT_TAB (pin to a dedicated tab so the
operator's chat tabs are never navigated away).

Usage:
  PATIENT_TAB=<tabid> python3 scripts/launch_patient.py <session-name> <prompt-file.md>

Output lands in scripts/logs/patient_<name>.log.
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

log_path = os.path.join(BASE, "logs", f"patient_{name}.log")
out = open(log_path, "a")
env = dict(os.environ)
p = subprocess.Popen(
    ["/home/z/.venv/bin/python3", "-u",
     os.path.join(BASE, "patient_dispatch.py"), name, prompt_file],
    stdout=out, stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True, cwd=ROOT, env=env)
out.close()
print(f"patient {name} detached (pid {p.pid}); log: {log_path}")
