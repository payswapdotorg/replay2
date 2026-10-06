#!/usr/bin/env python3
"""deploy_watch.py — the W151 deploy-window watcher (2026-10-06).

Mission (worklog Task 76 / replay-lanes.json queued_next):
  main @ 28d7244 is the deploy candidate (b6101d0 code + W145 wiring +
  the W151 R1 closure + docs). The Vercel account's 100/day deployment
  quota resets ~19:08Z Oct 6 (the API's limit.reset, read 19:10Z Oct 5;
  GitHub statuses on befa5fc/1dc9d30/b6101d0 all showed
  failure/build-rate-limit through 04:2xZ Oct 6).

Phases:
  WAIT    (now -> 18:30Z): heartbeat log every 10 min (cheap status read)
  PROBE   (18:30Z -> open): every 20 min, push ONE empty nudge commit to
           main ("deploy: probe the quota window — empty commit, no code
           change") and read the commit's GitHub statuses. A status of
           failure+build-rate-limit => still closed (next probe in 20 min).
           Any OTHER status (pending/success/failure-other) => the window
           is OPEN -> DEPLOY phase.
  DEPLOY  (open -> terminal): poll the tip commit's statuses every 60s
           until state=success (deployment READY) or failure. On success:
           curl the production URL (200 + FleetOS marker) and write
           flags/deploy_ready.json for the spot-check phase. On failure:
           write flags/deploy_failed.json with the status details.

The GitHub statuses API is the free Vercel oracle (the Vercel API token
was wiped with .secrets-env and is NOT needed on this path).

State survives session death: this log + the flags files + the worklog.
Spot-check runbook: /home/z/my-project/replay-packets/spot-check-runbook.md
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

WT = "/home/z/fleetos"              # main-tracking clone (push rights); self-heals on reset
CLONE_URL = "https://x-access-token:{PAT}@github.com/payswapdotorg/Fleetos.git"
FLAGS = "/home/z/replay2/scripts/flags"
LOG = "/home/z/replay2/scripts/logs/deploy_watch.log"
REPO = "payswapdotorg/Fleetos"
PAT_FILE = "/home/z/.payswap-env"
PROD_URL = "https://fleetos-staging-flame.vercel.app"

PROBE_START_EPOCH = None  # set below from the UTC clock
PROBE_INTERVAL = 20 * 60
DEPLOY_POLL = 60


def log(msg):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def pat():
    for line in open(PAT_FILE):
        if line.startswith("GITHUB_PAT="):
            return line.strip().split("=", 1)[1]
    raise SystemExit("no PAT in .payswap-env")


def statuses(sha):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/commits/{sha}/statuses",
        headers={"Authorization": f"token {pat()}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def vercel_status(sha):
    """Return (state, target) of the Vercel status on a commit, or (None, None)."""
    try:
        for s in statuses(sha):
            if str(s.get("context", "")).lower().startswith("vercel"):
                return s.get("state"), s.get("target_url") or ""
    except Exception as e:
        log(f"status read error: {e}")
    return None, None


def ensure_wt():
    """Self-heal: re-clone the main-tracking worktree if a sandbox reset wiped it.
    (2026-10-06 08:1xZ lesson: the daemon died on the wiped /home/z/fleetos-w151
    hardcode; the clone must never be a single point of failure again.)"""
    if os.path.isdir(os.path.join(WT, ".git")):
        return
    log(f"worktree {WT} missing — re-cloning from origin (self-heal)")
    url = CLONE_URL.replace("{PAT}", pat())
    r = subprocess.run(["git", "clone", "--quiet", url, WT],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("self-heal clone failed: " + r.stderr.strip()[:300])
    log(f"self-heal clone OK (main @ {tip()[:12]})")


def git(*args):
    r = subprocess.run(["git", "-C", WT, *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout.strip()


def tip():
    return git("rev-parse", "main")


def nudge():
    git("commit", "--allow-empty", "-m",
        "deploy: probe the Vercel quota window — empty commit, no code change "
        "(the 19:08Z reset; the deploy candidate is the W151 merge 28d7244)")
    git("push", "origin", "main")
    sha = tip()
    log(f"nudge pushed: {sha[:12]}")
    return sha


def prod_check():
    try:
        req = urllib.request.Request(PROD_URL, headers={"User-Agent": "deploy-watch"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode(errors="replace")
            return r.status, ("FleetOS" in body)
    except Exception as e:
        return None, str(e)[:120]


def main():
    os.makedirs(FLAGS, exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    ensure_wt()
    # PROBE_START = 18:30Z Oct 6 2026 UTC
    import calendar
    probe_start = calendar.timegm(time.strptime("2026-10-06 18:30:00", "%Y-%m-%d %H:%M:%S"))
    log(f"deploy_watch UP (candidate main @ 28d7244; probe start 18:30Z; quota reset est. 19:08Z)")
    last_probe = 0.0
    while True:
        now = time.time()
        try:
            sha = tip()
        except Exception as e:
            log(f"tip() failed ({str(e)[:120]}) — attempting self-heal")
            try:
                ensure_wt()
                sha = tip()
            except Exception as e2:
                log(f"self-heal failed: {str(e2)[:200]} — retry in 10 min")
                time.sleep(600)
                continue
        state, target = vercel_status(sha)
        if state == "success":
            code, marker = prod_check()
            log(f"DEPLOYED: {sha[:12]} status=success target={target[:60]} prod={code}/{marker}")
            with open(f"{FLAGS}/deploy_ready.json", "w") as f:
                json.dump({"commit": sha, "status": "success", "target": target,
                           "prod_http": code, "prod_marker": marker,
                           "ready_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
            log("flags/deploy_ready.json written — the spot-check phase may proceed")
            return 0
        if now < probe_start:
            log(f"WAIT: tip {sha[:12]} status={state} target={target[:50]} (probe starts 18:30Z)")
            time.sleep(600)
            continue
        # PROBE phase
        if state == "failure" and "build-rate-limit" not in target:
            # a REAL build failure (not the quota) — terminal for this attempt
            log(f"DEPLOY FAILED (non-quota): {sha[:12]} target={target[:80]}")
            with open(f"{FLAGS}/deploy_failed.json", "w") as f:
                json.dump({"commit": sha, "status": state, "target": target,
                           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
            return 2
        if state is not None and "build-rate-limit" not in target:
            # window OPEN: building or otherwise active on this commit
            log(f"WINDOW OPEN: tip {sha[:12]} status={state} target={target[:60]} — polling")
            time.sleep(DEPLOY_POLL)
            continue
        if now - last_probe >= PROBE_INTERVAL:
            sha = nudge()
            last_probe = now
            time.sleep(90)
            state, target = vercel_status(sha)
            log(f"probe status: {state} target={target[:60]}")
            if state is not None and "build-rate-limit" not in target:
                log("window OPEN — entering DEPLOY poll")
            continue
        log(f"PROBE wait: tip {sha[:12]} status={state} (rate-limited); next nudge in "
            f"{int((PROBE_INTERVAL - (now - last_probe)) / 60)} min")
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main())
