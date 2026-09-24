#!/usr/bin/env python3
"""launch_patient.py — patient_dispatch.py, fully detached (lesson-13).

RECREATED 2026-09-24 during sandbox-reset recovery: the original launcher
was working-copy-only and died with the sandbox (lesson-122 violation —
this copy is committed to the repo so the next reset cannot lose it).

Concurrent-wave pin doctrine (2026-09-21/24): opens a FRESH chat.z.ai home
tab and pins the dispatch to it via PATIENT_TAB — patient_dispatch
navigates its tab to home for the New Task surface, so it must never be
pointed at a live worker-chat tab. One dispatch = one dedicated tab.

Usage: python3 launch_patient.py <session-name> <prompt-file.md>
Output: scripts/logs/create_<name>.log  (the auto_pipeline CREATE_LOG contract —
        the 2026-09-24 reset recreation first wrote patient_<name>.log and the
        pipeline's create_verdict read no-log; path now matches the contract)
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

if len(sys.argv) != 3:
    print(__doc__)
    sys.exit(2)

name, prompt_file = sys.argv[1], os.path.abspath(sys.argv[2])
log_path = os.path.join(BASE, "logs", f"create_{name}.log")

# Dispatch tab discipline: reuse ONLY the tab this launcher itself pinned
# (flags/patient_tab_pin.txt) — never an arbitrary home tab (the 17:48
# W098 incident reused the OPERATOR's login tab: the send mislanded at an
# old chat URL with a false-positive verify). If no pinned tab exists or
# it is no longer a chat.z.ai home tab, open a fresh one and pin THAT.
pin = ""
PINFILE = os.path.join(BASE, "flags", "patient_tab_pin.txt")
try:
    prev = ""
    try:
        prev = open(PINFILE).read().strip()
    except Exception:
        pass
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if prev:
        cand = [t for t in tabs
                if (t.get("id") or "").upper().startswith(prev.upper())
                and (t.get("url") or "").rstrip("/") == "https://chat.z.ai"]
        if cand:
            pin = (cand[0].get("id") or "")[:8]
            print(f"reusing pinned home tab {pin}")
    if not pin:
        homes = [t for t in tabs
                 if (t.get("url") or "").rstrip("/") == "https://chat.z.ai"]
        # only adopt an unpinned home tab when none was ever pinned AND it
        # is not the login tab (heuristic: the tab whose id is NOT in the
        # registry history) — safest is always a FRESH tab here:
        tab = channel.new_tab("https://chat.z.ai/")
        pin = (tab.get("id") or "")[:8]
        print(f"fresh dispatch tab {pin}")
    os.makedirs(os.path.dirname(PINFILE), exist_ok=True)
    open(PINFILE, "w").write(pin)
except Exception as e:
    print(f"WARN: tab selection failed ({e}) — launching unpinned "
          "(safe only when no other dispatch is running)")

env = dict(os.environ)
if pin:
    env["PATIENT_TAB"] = pin

p = subprocess.Popen(
    [os.environ.get("PYTHON_BIN", "/home/z/.venv/bin/python3"),
     os.path.join(BASE, "patient_dispatch.py"), name, prompt_file],
    stdout=open(log_path, "a"), stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL, start_new_session=True,
    cwd=os.path.dirname(BASE), env=env)
print(f"patient dispatch {name} detached (pid {p.pid}, pin {pin or '-'}); "
      f"log: {log_path}")
