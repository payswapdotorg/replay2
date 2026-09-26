#!/usr/bin/env python3
"""w3_relay.py — keep re-launching Wave-3 creates until all three sessions are sent.

Peak-hours menu churn removes GLM-5.3 from the model menu; dispatch_worker.py
exhausts its assault rounds and dies WITHOUT arming recover_capacity (the rc=2
model-menu path). This relay re-launches creates every ~8 minutes until the
registry shows flauz-F-w3, flauz-G-w3 and flauz-H-w3 with sent=True (or a url
landed). Detached-safe: launched via launch_detached.py.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(BASE, "flags", "session_registry.jsonl")

NAMES = ["flauz-F3-w3"]
PROMPTS = {
    "flauz-F3-w3": os.path.join(BASE, "worker-prompts", "flauz-w3-f.md"),
}


def latest_rows():
    rows = {}
    try:
        with open(REG) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                n = d.get("name")
                if n:
                    rows[n] = d
    except FileNotFoundError:
        pass
    return rows


def sent_or_landed(row):
    return bool(row.get("sent")) or bool(row.get("url"))


def void_half(name):
    try:
        subprocess.run(
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"), "void", name,
             "relay: unsent half-row cleanup before relaunch"],
            capture_output=True, timeout=90)
    except Exception:
        pass


def main():
    log = open(os.path.join(BASE, "logs", "w3_relay2.log"), "a")
    start = time.time()
    while time.time() - start < 4 * 3600:  # 4h budget
        rows = latest_rows()
        pending = [n for n in NAMES if not sent_or_landed(rows.get(n, {}))]
        if not pending:
            log.write(f"[{time.strftime('%H:%M:%S')}] all Wave-3 sessions sent/url — relay exits\n")
            log.flush()
            return
        for n in pending:
            row = rows.get(n, {})
            if row and not row.get("sent") and not row.get("url"):
                # half-row from a dead create — clean it so create() can run fresh
                void_half(n)
            log.write(f"[{time.strftime('%H:%M:%S')}] relaunch create {n}\n")
            log.flush()
            subprocess.Popen(
                [sys.executable, os.path.join(BASE, "launch_create.py"), n, PROMPTS[n]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(480)  # 8 min between waves (create assault itself runs ~10 min)
    log.write(f"[{time.strftime('%H:%M:%S')}] relay budget exhausted\n")
    log.flush()


if __name__ == "__main__":
    main()
