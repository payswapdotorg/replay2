#!/usr/bin/env python3
"""dispatch_wave3.py — CamScan wave-3 auto-dispatcher (reset #12 recovery).

Polls the console /api/status (bridge status). When the operator is logged in
at chat.z.ai through the replay image (browser_login startswith 'logged-in'),
fires the two wave-3 worker creates via dispatch_worker.py (dfork-launched,
80s spacing between creates, 15-min register-wait per round, 3 rounds max,
registry-idempotent: a registry record with name+sent and no action key IS a
live create — mirror dispatch_worker's own _find semantics).
"""
import json
import os
import subprocess
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATUS_URL = "http://127.0.0.1:3000/api/status"
SPACING_S = 80          # between the two creates in one round
REGISTER_WAIT_S = 900   # 15-min register-wait per round
MAX_ATTEMPTS = 3

PY = "python3"
_pbt = os.path.join(BASE, "python_bin.txt")
if os.path.exists(_pbt):
    with open(_pbt) as f:
        cand = f.read().strip()
        if cand:
            PY = cand

PACKETS = [
    ("camscan-prod-011", os.path.join(BASE, "worker-prompts", "camscan-prod-011.md")),
    ("camscan-prod-012", os.path.join(BASE, "worker-prompts", "camscan-prod-012.md")),
]


def outbox(text):
    with open(OUTBOX, "a") as f:
        f.write(json.dumps({"ts": time.time(), "from": "agent", "text": text}) + "\n")


def status():
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=30) as r:
            return json.loads(r.read().decode()).get("browser_login", "unknown")
    except Exception as e:  # noqa: BLE001 - status errors are values, not crashes
        return "error:%s" % e


def registry_names():
    """Names with a live create record (name+sent, not voided, no action key)."""
    names = set()
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                n = d.get("name")
                if n and d.get("sent") and not d.get("voided"):
                    names.add(n)
    except FileNotFoundError:
        pass
    return names


def launch_create(name, packet):
    log = os.path.join(BASE, "logs", "dispatch-%s.log" % name)
    # 2026-10-02 17:40 fix (lead, wave-3 forensic): this used
    # dispatch_worker.py "send" — but send() only works on EXISTING sessions
    # (prints 'no session named X', rc=1) and never creates anything. The
    # dispatcher silently no-op'd for two full attempts. create() takes the
    # RAW prompt-file path (no '@' prefix) and does _subst_pat itself.
    subprocess.call(
        [PY, os.path.join(BASE, "dfork_launch.py"), log,
         PY, os.path.join(BASE, "dispatch_worker.py"), "create", name, packet]
    )


def main():
    outbox("dispatch_wave3 ARMED (reset #12): polling for operator login every 15s; on logged-in fires "
           "camscan-prod-011 (advanced tools) + camscan-prod-012 (specialist modes) — disjoint paths, "
           "parallel dispatch legal per board rules.")
    attempts = {}
    while True:
        st = status()
        if not st.startswith("logged-in"):
            time.sleep(15)
            continue

        have = registry_names()
        todo = [(n, p) for (n, p) in PACKETS if n not in have]
        if not todo:
            outbox("wave-3 dispatch COMPLETE: both sessions registered in the registry.")
            return

        fired_any = False
        for i, (name, packet) in enumerate(todo):
            if attempts.get(name, 0) >= MAX_ATTEMPTS:
                continue
            launch_create(name, packet)
            attempts[name] = attempts.get(name, 0) + 1
            fired_any = True
            outbox("login detected (browser_login=%s) -> dispatch FIRED (attempt %d/%d): %s"
                   % (st, attempts[name], MAX_ATTEMPTS, name))
            if i < len(todo) - 1:
                time.sleep(SPACING_S)

        if not fired_any:
            outbox("wave-3 dispatch EXHAUSTED: %d attempts each, no registry records — lead attention needed "
                   "(check logs/dispatch-camscan-prod-*.log for the capacity-fight outcome)."
                   % MAX_ATTEMPTS)
            return
        time.sleep(REGISTER_WAIT_S)


if __name__ == "__main__":
    main()
