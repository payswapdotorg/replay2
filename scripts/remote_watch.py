#!/usr/bin/env python3
"""remote_watch.py [--repo owner/name] — read-only origin watcher.

Polls git ls-remote every CYCLE_S and notes NEW/MOVED/GONE refs into
flags/agent_outbox.jsonl for the TL. Never pushes, never merges, never
creates anything — observation only.

2026-10-02 doctrine: with a parallel TL session shepherding the same repo
from another instance, the coordination surface is the repo itself. This
watcher is how THIS session learns about the parallel session's worker
deliveries (work/* branches) and merges (main movement) without ever
interfering: no re-dispatch of its lanes, no merges of its branches.

PAT: --pat argument, or RW_PAT env, or /home/z/.payswap-env GITHUB_PAT.
Repo: --repo argument (REQUIRED — §0: no project repo is hardcoded here).
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
SNAP = os.path.join(FLAGS, "remote_refs_snapshot.json")
CYCLE_S = 600


def log(m):
    print(f"[remote_watch {time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {m}", flush=True)


def outbox(note):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "name": "remote-watch", "note": note}) + "\n")
    except Exception:
        pass


def pat_from_env():
    for cand in (os.environ.get("RW_PAT"),):
        if cand:
            return cand
    try:
        return open("/home/z/.payswap-env").read().split("GITHUB_PAT=")[1].split()[0].strip()
    except Exception:
        return ""


def refs(repo, pat):
    r = subprocess.run(
        ["git", "ls-remote", f"https://x-access-token:{pat}@github.com/{repo}.git"],
        capture_output=True, text=True, timeout=90)
    out = {}
    for line in (r.stdout or "").split("\n"):
        m = re.match(r"([0-9a-f]{40})\s+(refs/heads/\S+)", line.strip())
        if m:
            out[m.group(2)] = m.group(1)
    if not out:
        raise RuntimeError(f"ls-remote empty/failed: {(r.stderr or '')[:120]}")
    return out


def main():
    repo = ""
    if "--repo" in sys.argv:
        repo = sys.argv[sys.argv.index("--repo") + 1]
    if not repo:
        print("--repo owner/name is required (§0: no project repo is hardcoded here) — exiting", file=sys.stderr)
        return 2
    pat = pat_from_env()
    if "--pat" in sys.argv:
        pat = sys.argv[sys.argv.index("--pat") + 1]
    if not pat:
        print("no PAT (RW_PAT env / --pat / .payswap-env) — exiting", file=sys.stderr)
        return 2
    os.makedirs(FLAGS, exist_ok=True)
    prev = refs(repo, pat)
    json.dump(prev, open(SNAP, "w"), indent=1)
    log(f"repo {repo}: baseline {len(prev)} refs, main @{prev.get('refs/heads/main', '?')[:8]}, "
        f"sim={[k.split('/')[-1] for k in prev if k.startswith('refs/heads/sim/')]}")
    outbox(f"REMOTE-WATCH armed: {repo} — {len(prev)} refs, main @{prev.get('refs/heads/main', '?')[:8]}")
    while True:
        try:
            open(os.path.join(FLAGS, "remote_watch_heartbeat"), "w").write(str(int(time.time())))
        except Exception:
            pass
        time.sleep(CYCLE_S)
        try:
            cur = refs(repo, pat)
        except Exception as e:
            log(f"ls-remote failure: {e}")
            continue
        for k, v in sorted(cur.items()):
            if k not in prev:
                note = f"NEW REF {repo} {k} @{v[:8]}"
                log(note)
                outbox(note)
            elif prev[k] != v:
                note = f"REF MOVED {repo} {k} {prev[k][:8]} -> {v[:8]}"
                log(note)
                outbox(note)
        for k in sorted(prev):
            if k not in cur:
                note = f"REF GONE {repo} {k}"
                log(note)
                outbox(note)
        prev = cur
        json.dump(prev, open(SNAP, "w"), indent=1)


if __name__ == "__main__":
    main()
