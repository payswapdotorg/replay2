"""launch_vpn_probe.py — start the passive vpn_probe.py detached (orphan to
init via immediate-exit launcher, per AGENT_BOOT_PROMPT learning 13)."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

p = subprocess.Popen(
    [PY, os.path.join(BASE, "vpn_probe.py")],
    stdout=open("/tmp/vpn_probe.err", "w"),
    stderr=subprocess.STDOUT,
    start_new_session=True, cwd=BASE)
open("/tmp/vpn_probe.pid", "w").write(str(p.pid))
print("vpn_probe detached pid", p.pid, "-> /tmp/vpn_probe.log")
