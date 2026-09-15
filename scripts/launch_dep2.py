#!/usr/bin/env python3
"""launch_dep2.py — re-dispatch DEP-020 + DEP-001 via dep_land.py (detached,
staggered 60s to avoid create-race on the browser surface)."""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))

for i, (name, prompt) in enumerate((
        ("dep-020", "worker-prompts/dep-020.md"),
        ("dep-001", "worker-prompts/dep-001.md"))):
    out = open(os.path.join(BASE, "logs", f"dep_land2_{name}.log"), "w")
    p = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "dep_land.py"),
         name, os.path.join(BASE, prompt), "75", "15"],
        stdout=out, stderr=subprocess.STDOUT,
        start_new_session=True, cwd=BASE)
    print(f"dep_land loop for {name}: pid {p.pid}")
    if i == 0:
        time.sleep(60)
