"""launch_detached.py — run ANY command fully detached (lesson-13 pattern).

Usage:
  python3 scripts/launch_detached.py <log-path> <cmd> [args...]

The child gets start_new_session=True so the tool-shell process-group
kill never touches it. Verify via the log file; never trust return alone.
"""
import os
import subprocess
import sys

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

log_path = sys.argv[1]
cmd = sys.argv[2:]
os.makedirs(os.path.dirname(log_path) or "/tmp", exist_ok=True)
out = open(log_path, "a")
p = subprocess.Popen(
    cmd, stdout=out, stderr=subprocess.STDOUT,
    start_new_session=True, cwd=os.path.dirname(os.path.abspath(__file__)))
out.flush()
print(f"detached (pid {p.pid}); log: {log_path}")
