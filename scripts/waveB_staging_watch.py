#!/usr/bin/env python3
"""waveB_staging_watch.py — delivery-staging observer (API-outage fallback).

The chat-detail API (batch store) can 500 for hours during recovery, which
blinds the report-gate completion watcher. The workspaces FILES api stays
up (different service). This watcher polls each sandbox's ls-tree for the
appearance of `delivery/DELIVERY.txt` — the packet's manifest step, which
the worker writes AFTER staging completes, right before its final report.

On detection: writes flags/<name>-staged.marker (Lead-internal pre-harvest
signal; the operator-facing event remains the completion ping). Passive
only — no dispatch power, no tab manipulation.

Usage: waveB_staging_watch.py <name>:<chat-id>:<workspace-id> [...] [--every 180]
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
TOK = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')
API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"


def log(line):
    print(time.strftime("[%H:%M:%S]") + f" [stage-watch] {line}", flush=True)


def ls_tree(chat, ws):
    req = urllib.request.Request(
        f"{API}/ls-tree", data=json.dumps({"chatId": chat, "workspace_id": ws}).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {TOK}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        entries = json.loads(r.read().decode())
    if isinstance(entries, dict):
        entries = entries.get("tree") or entries.get("data") or []
    return [e for e in entries if isinstance(e, str)]


def main():
    jobs, every, max_s = [], 180, 14 * 3600
    for a in sys.argv[1:]:
        if a.startswith("--every"):
            every = int(a.split("=", 1)[1])
        elif a.count(":") >= 2:
            n, c, w = a.split(":", 2)
            jobs.append((n, c, w))
    if not jobs:
        print(__doc__)
        return 2
    staged = set()
    for n, _, _ in jobs:
        if os.path.exists(os.path.join(FLAGS, f"{n}-staged.marker")):
            staged.add(n)
    log(f"watching {[(n, c[:8]) for n, c, _ in jobs]}; already staged: {sorted(staged) or 'none'}")
    t0 = time.time()
    while len(staged) < len(jobs) and time.time() - t0 < max_s:
        time.sleep(every)
        for n, c, w in jobs:
            if n in staged:
                continue
            try:
                entries = ls_tree(c, w)
            except Exception as e:
                log(f"{n}: ls-tree error {str(e)[:60]}")
                continue
            if any(e == "delivery/DELIVERY.txt" for e in entries):
                dcount = len([e for e in entries if e.startswith("delivery/")])
                staged.add(n)
                open(os.path.join(FLAGS, f"{n}-staged.marker"), "w").write(
                    f"{n} staged delivery/ ({dcount} files + DELIVERY.txt) at {time.strftime('%H:%M:%S')}\n")
                log(f"{n} STAGED — delivery/ tree present ({dcount} files) — pre-harvest signal")
    log(f"done; staged={sorted(staged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
