#!/usr/bin/env python3
"""launch_peak_retry.py — start a detached peak_retry.py daemon
(orphan to init via immediate-exit launcher, per learning 13).

Usage: launch_peak_retry.py <url_sub>[,<url_sub>...] [cadence]
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

if len(sys.argv) < 2:
    print("usage: launch_peak_retry.py <url_sub>[,<url_sub>...] [cadence]")
    sys.exit(1)

subs = sys.argv[1]
cadence = sys.argv[2] if len(sys.argv) > 2 else "150"

p = subprocess.Popen(
    [PY, os.path.join(BASE, "peak_retry.py"), subs, "--cadence", cadence],
    stdout=open("/tmp/peak_retry.log", "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
print(f"peak_retry detached pid {p.pid} -> /tmp/peak_retry.log (subs={subs} cadence={cadence}s)")
