#!/usr/bin/env python3
"""recover_capacity.py — PERSISTENT AGGRESSIVE capacity assault (operator policy).

Operator (2026-09-09): "do not wait just because a popup tells you to, never
wait, find a way around it ... normally cancelling and retrying works just as
long as you always pick the right model (GLM 5.3), the agents tab and the
full stack skill before resending the prompt."

So this poller NEVER waits out a GLM-5.3 capacity peak: it re-runs the full
verified dispatch (dispatch_worker.create — agents tab + GLM-5.3 + Full-Stack
+ insert + send, cancelling every capacity popup it meets and re-picking the
selections) round after round until the task actually lands and generates.
The supervisor keeps one poller alive PER flag file while it exists; success
(or an already-live session) clears the flag.

Usage: recover_capacity.py [flag-path] [legacy-uuid]
  flag-path  — flags/capacity_recover[.<name>].json (per-session; the
               supervisor passes it explicitly). Defaults to the legacy
               single-slot path for manual invocation.

Flag format: {"name": ..., "prompt_file": ..., "uuid": ..., "tab_id": ...}
Legacy flags {"uuid": ...} are resolved through the session registry.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
# argv[1] = flag path (supervisor passes the per-session flag); argv[1] may
# also be a bare legacy uuid (old supervisor invocation) — detect by suffix.
_arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
if _arg1.endswith(".json"):
    FLAG = os.path.abspath(_arg1)
    _legacy_uuid = sys.argv[2] if len(sys.argv) > 2 else ""
elif _arg1:
    FLAG = os.path.join(BASE, "flags/capacity_recover.json")
    _legacy_uuid = _arg1
else:
    FLAG = os.path.join(BASE, "flags/capacity_recover.json")
    _legacy_uuid = ""
_stem = os.path.basename(FLAG)[len("capacity_recover"):-len(".json")] or ""
PIDFILE = os.path.join(BASE, f"flags/capacity_recover.pid{_stem}")
REG = os.path.join(BASE, "flags/session_registry.jsonl")


def _clear_flag():
    for p in (FLAG, PIDFILE):
        try:
            os.remove(p)
        except Exception:
            pass


def _spec():
    """Resolve (name, prompt_file) from the flag — legacy-registry aware."""
    d = json.load(open(FLAG))
    if d.get("name") and d.get("prompt_file"):
        return d
    uuid = d.get("uuid", "")
    try:
        lines = open(REG).read().split("\n")
    except Exception:
        lines = []
    for line in reversed([l for l in lines if l.strip()]):
        try:
            s = json.loads(line)
        except Exception:
            continue
        if s.get("stage") == "capacity" and (
                uuid in (s.get("url") or "") or (s.get("tab_id") or "").startswith(uuid)):
            d["name"] = s.get("name")
            d["prompt_file"] = s.get("prompt_file")
            return d
    return None


def main():
    spec = _spec()
    if not spec or not spec.get("name") or not spec.get("prompt_file"):
        print("flag unresolvable (no name/prompt_file) — clearing", flush=True)
        _clear_flag()
        return 4
    name, prompt_file = spec["name"], spec["prompt_file"]
    print(f"aggressive recovery: {name} <- {prompt_file} (never waits out capacity)", flush=True)
    for attempt in range(240):  # up to ~8h of active assault; supervisor re-arms
        rc = subprocess.call([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                              "create", name, prompt_file])
        print(f"[{attempt}] create rc={rc}", flush=True)
        if rc == 0:
            _clear_flag()
            return 0
        if rc == 1:
            print("session already live — recovered elsewhere", flush=True)
            _clear_flag()
            return 0
        # rc==3: create ran its full in-process assault and re-staged the
        # flag; go again immediately (short gap). rc==2/other: give the page
        # a moment, then the next create closes stale tabs and retries.
        time.sleep(20 if rc == 3 else 45)
    return 3


if __name__ == "__main__":
    try:
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    sys.exit(main())
