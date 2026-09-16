#!/usr/bin/env python3
"""Drill: plant a durable squatter on :3000 to exercise the supervisor PORT GUARD."""
import subprocess
import time

# kill current console (simulate post-reset state) — bracket trick so pkill
# never matches this script's own cmdline
subprocess.run(["pkill", "-f", "replay2.*next [d]ev"], capture_output=True)
subprocess.run(["pkill", "-f", "next[-]server"], capture_output=True)
time.sleep(2)

# plant durable squatter: detached, cwd=/home/z/my-project, no console body
logf = open("/tmp/squatter2.log", "w")
p = subprocess.Popen(
    ["python3", "-m", "http.server", "3000"],
    cwd="/home/z/my-project",
    start_new_session=True,
    stdout=logf,
    stderr=subprocess.STDOUT,
)
with open("/tmp/squatter2.pid", "w") as f:
    f.write(str(p.pid))
print(f"squatter planted, pid {p.pid}", flush=True)
