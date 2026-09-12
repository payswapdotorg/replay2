"""launch_send.py — dispatch_worker.py send, fully detached.

Lesson-13 pattern applied to SENDS (learned the hard way 2026-09-12: two
foreground sends died at the tool-shell timeout mid-assault, leaving
staged composers and navigated tabs). A send that fights popups can need
>10 min; a tool-shell timeout must never kill it mid-round.

Usage:
  python3 scripts/launch_send.py <session-name> <msg-or-@file>

Output lands in scripts/logs/send_<name>.log; verify landing via
check_chats.py (message count growth) — never trust the log alone.
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(2)

name, msg = sys.argv[1], sys.argv[2]
if msg.startswith("@") and not os.path.isabs(msg[1:]):
    msg = "@" + os.path.abspath(os.path.join(os.getcwd(), msg[1:]))

log_path = os.path.join(BASE, "logs", f"send_{name}.log")
out = open(log_path, "a")
p = subprocess.Popen(
    [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "send", name, msg],
    stdout=out, stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
out.flush()
print(f"send {name} detached (pid {p.pid}); log: {log_path}")
