#!/usr/bin/env python3
"""launch_dep_watch.py — start dep_watch.py detached (survives Bash tool cleanup)."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
out = open(os.path.join(BASE, "logs", "dep_watch.out"), "w")
p = subprocess.Popen(
    [sys.executable, os.path.join(BASE, "dep_watch.py")],
    stdout=out, stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
print("dep_watch pid", p.pid)
