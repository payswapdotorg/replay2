#!/usr/bin/env python3
"""launch_parked_watch.py — start a detached parked_watch.py for one session
(orphan to init via immediate-exit launcher, learning 13).

Usage: launch_parked_watch.py <name> <chat-id> [marker] [prompt-file]
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

if len(sys.argv) < 3:
    print("usage: launch_parked_watch.py <name> <chat-id> [marker] [prompt-file]")
    sys.exit(1)

name, chat_id = sys.argv[1], sys.argv[2]
marker = sys.argv[3] if len(sys.argv) > 3 else "COMPLETION REPORT"
prompt_file = sys.argv[4] if len(sys.argv) > 4 else ""

args = [PY, os.path.join(BASE, "parked_watch.py"), name, chat_id, marker]
if prompt_file:
    args.append(prompt_file)

p = subprocess.Popen(args, stdout=open(f"/tmp/parked_watch_{name}.log", "w"),
                     stderr=subprocess.STDOUT, start_new_session=True, cwd=BASE)
print(f"parked_watch[{name}] detached pid {p.pid} -> /tmp/parked_watch_{name}.log")
