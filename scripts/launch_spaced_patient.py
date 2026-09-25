#!/usr/bin/env python3
"""launch_spaced_patient.py — patient retry loop around launch_patient.py.

2026-09-25 (wave-6 phantom grind): the New-Task create-gate swallows sends
while other generations are active (w020f/w020g phantoms: chat shell 500s,
packet never committed). spaced_create.py loops the OLD launch_create path,
which lacks the 2026-09-25 send hardening (Escape+DOM-click, send-readiness
gate, freshness gate). This wrapper loops the PROVEN patient_dispatch path:

  one launch_patient <base><n> per interval, fresh session name per attempt
  (registry discipline: never reuse a name), verdict read from
  create_<name>.log + registry (sent:true = LANDED), exit 0 on landing.

Usage: launch_spaced_patient.py <base-name> <prompt-file> [interval-s, def 240]
Env: SPACED_MAX (default 12 attempts)
Output: logs/spaced_<base>.log
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(BASE, "logs")
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

base_name, prompt_file = sys.argv[1], os.path.abspath(sys.argv[2])
interval = int(sys.argv[3]) if len(sys.argv) > 3 else 240
MAX = int(os.environ.get("SPACED_MAX", "12"))

os.makedirs(LOGDIR, exist_ok=True)
log_path = os.path.join(LOGDIR, f"spaced_{base_name}.log")
log = open(log_path, "a", buffering=1)


def say(msg):
    line = f"[{base_name}] {time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    log.write(line + "\n")


def registry_sent(name):
    """True iff the registry holds a sent:true landing for name."""
    try:
        for raw in open(REG).read().splitlines():
            if not raw.strip():
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if d.get("name") == name and d.get("sent") and d.get("action") not in ("void", "failed"):
                return True
    except FileNotFoundError:
        pass
    return False


def wait_verdict(name, timeout=420):
    """Poll create_<name>.log until a verdict line appears or timeout."""
    cl = os.path.join(LOGDIR, f"create_{name}.log")
    deadline = time.time() + timeout
    verdict = None
    while time.time() < deadline:
        try:
            tail = open(cl).read()[-400:]
        except FileNotFoundError:
            time.sleep(10)
            continue
        if "server-verified packet landing" in tail or "SENT-VERIFIED" in tail:
            return "landed"
        m = re.search(r"ERROR: (.{0,90})", tail)
        if m:
            verdict = m.group(1).strip()
        if "send FAILED server-side" in tail:
            return "failed"
        time.sleep(10)
    return "timeout:" + (verdict or "no-verdict")


say(f"spaced patient loop: prompt={os.path.basename(prompt_file)} "
    f"interval={interval}s max={MAX}")
for attempt in range(1, MAX + 1):
    name = f"{base_name}{attempt}"
    say(f"attempt {attempt}/{MAX} as {name}")
    r = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_patient.py"), name, prompt_file],
        capture_output=True, text=True, timeout=120)
    say(f"launcher: {(r.stdout or '').strip().splitlines()[-1][:100] if (r.stdout or '').strip() else r.stderr.strip()[:100]}")
    verdict = wait_verdict(name)
    say(f"verdict: {verdict}")
    if verdict == "landed" or registry_sent(name):
        say(f"LANDED server-side as {name}")
        sys.exit(0)
    if attempt < MAX:
        say(f"sleeping {interval}s before next attempt")
        time.sleep(interval)
say(f"EXHAUSTED {MAX} attempts without landing")
sys.exit(4)
