#!/usr/bin/env python3
"""Launch delivery_watch.py fully detached (bash tool kills descendants)."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
name, tab_prefix, session_url, msg_file, marker = sys.argv[1:6]
logf = open(os.path.join(BASE, "logs", "delivery-watch.out"), "a")
p = subprocess.Popen(
    [sys.executable, os.path.join(BASE, "delivery_watch.py"),
     name, tab_prefix, session_url, msg_file, marker],
    stdout=logf, stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
print(f"delivery_watch[{name}] pid={p.pid}")
