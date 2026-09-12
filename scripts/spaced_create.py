#!/usr/bin/env python3
"""spaced_create.py — patient single-round create loop for gate-blocked dispatches.

The 13-round create assault burns allowance into the same cooldown and
wedges renderers (lesson 61/66); the queue_watch zombie-tab churn on
phantom sessions is worse. This loop: ONE create round (DW_ROUNDS=1) per
interval, server-verified (create() only returns ACCEPTED when the chat
exists server-side with the packet committed).

Usage: spaced_create.py <session-name> <prompt-file> [interval-s, default 240]

Exit 0 when the session lands server-side; 4 after MAX attempts.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)

name, prompt = sys.argv[1], sys.argv[2]
prompt = os.path.abspath(prompt) if prompt.startswith("@") else prompt
prompt = prompt[1:] if prompt.startswith("@") else prompt
interval = int(sys.argv[3]) if len(sys.argv) > 3 else 240
MAX = int(os.environ.get("SPACED_MAX", "40"))


def _landed():
    """Chat exists server-side with a content-bearing user message."""
    reg = os.path.join(BASE, "flags", "session_registry.jsonl")
    url = None
    try:
        for line in open(reg).read().split("\n"):
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("name") != name:
                continue
            if d.get("action") in ("void", "failed", "done"):
                url = None
            elif d.get("url") and "/c/" in d.get("url", ""):
                url = d["url"]
    except Exception:
        pass
    if not url:
        return None
    cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(BASE, "probe_chat.py"), cid],
            cwd=BASE, capture_output=True, text=True, timeout=60)
        d = json.loads(out.stdout.strip().split("\n")[-1])
        if d.get("alive"):
            return cid
    except Exception:
        pass
    return None


for attempt in range(1, MAX + 1):
    stamp = time.strftime("%H:%M:%S")
    # already landed? (a previous round's create may have succeeded)
    cid = _landed()
    if cid:
        print(f"[{name}] {stamp} chat LANDED server-side ({cid[:8]}) — done", flush=True)
        sys.exit(0)
    print(f"[{name}] {stamp} spaced create attempt {attempt}/{MAX} (1 round)", flush=True)
    env = dict(os.environ, DW_ROUNDS="1")
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
             "create", name, prompt],
            cwd=BASE, env=env, capture_output=True, text=True, timeout=300)
        out = (p.stdout or "") + (p.stderr or "")
        lines = [l for l in out.split("\n") if l.strip()]
        verdict = lines[-1] if lines else "rc=%s" % p.returncode
        # a landed create prints ACCEPTED (server-verified) and rc 0
        if "ACCEPTED" in out and "server-verified" in out:
            print(f"[{name}] {stamp} LANDED: {verdict[:140]}", flush=True)
            sys.exit(0)
        print(f"[{name}] {stamp} verdict: {verdict[:140]}", flush=True)
    except subprocess.TimeoutExpired:
        print(f"[{name}] {stamp} create round timed out (300s) — next interval", flush=True)
    time.sleep(interval)

print(f"[{name}] exhausted {MAX} spaced create attempts", flush=True)
sys.exit(4)
