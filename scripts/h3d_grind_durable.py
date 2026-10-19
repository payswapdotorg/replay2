#!/usr/bin/env python3
"""h3d_grind_durable.py — durability watcher for the Task 20 verification loops.

The two resident loops (agent-browser grind + CDP companion) bank their
artifacts in /home/z/my-project/research/out — an EPHEMERAL sandbox path.
The GitHub repos are the only persistent artifact. This watcher:

  - every 30 min: snapshots the loop state (grind-state, cdp-cycles, logs
    tail) into replay2/ops-results/e2e20/ and pushes (rebase-safe: only
    additive paths under ops-results/)
  - the moment a SUCCESS marker appears (e2e20-neural-result.json with
    outcome=success, or e2e20-cdp-neural-success.json): copies the full
    e2e20 artifact set (results + neural screenshots), commits, pushes,
    writes e2e20-durable-success.json, and exits — the loops will have
    exited by then too.

Sources the PAT from browser-profile/ops-vault.env at startup.
"""
import json
import os
import shutil
import subprocess
import time

OUT = "/home/z/my-project/research/out"
REPO = "/home/z/replay2"
DEST = f"{REPO}/ops-results/e2e20"
LOG = f"{OUT}/e2e20-durable.log"
SUCCESS_FLAG = f"{OUT}/e2e20-durable-success.json"

SNAPSHOT_FILES = [
    "e2e20-grind-state.json",
    "e2e20-cdp-cycles.json",
    "e2e20-result.json",
]
SUCCESS_MARKERS = ["e2e20-neural-result.json", "e2e20-cdp-neural-success.json"]


def log(*args):
    line = time.strftime("[%Y-%m-%dT%H:%M:%SZ] ", time.gmtime()) + " ".join(str(a) for a in args)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def sh(cmd, cwd=None, timeout=90):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def git_push():
    env_pat = sh("grep -oP '(?<=^export GITHUB_PAT=).*' /home/z/my-project/browser-profile/ops-vault.env"
                 ).stdout.strip().strip('"')
    url = f"https://x-access-token:{env_pat}@github.com/payswapdotorg/replay2.git" if env_pat else None
    if not url:
        log("no PAT — cannot push")
        return False
    sh("git add ops-results/", cwd=REPO)
    r = sh("git -c user.name=orchestrator -c user.email=ops@payswap.org commit -m "
           f"'Task 20 durability: verification-loop artifacts snapshot ({time.strftime('%Y-%m-%d %H:%M', time.gmtime())}Z)'",
           cwd=REPO)
    if "nothing to commit" in (r.stdout + r.stderr):
        return True
    sh(f"git fetch {url} main", cwd=REPO)
    sh("GIT_EDITOR=true git rebase FETCH_HEAD", cwd=REPO)
    p = sh(f"git push {url} main:main", cwd=REPO, timeout=120)
    ok = "main -> main" in (p.stdout + p.stderr) or "Everything up-to-date" in (p.stdout + p.stderr)
    log("push:", ("OK" if ok else "FAILED"), "|", (p.stdout + p.stderr).strip().splitlines()[-1][:120] if (p.stdout+p.stderr).strip() else "")
    return ok


def snapshot():
    os.makedirs(DEST, exist_ok=True)
    changed = False
    for name in SNAPSHOT_FILES:
        src = f"{OUT}/{name}"
        if os.path.isfile(src):
            dst = f"{DEST}/{name}"
            try:
                old = open(dst).read() if os.path.isfile(dst) else None
                new = open(src).read()
                if old != new:
                    shutil.copy(src, dst)
                    changed = True
            except Exception:
                pass
    return changed


def check_success():
    for name in SUCCESS_MARKERS:
        p = f"{OUT}/{name}"
        if not os.path.isfile(p):
            continue
        try:
            d = json.load(open(p))
        except Exception:
            continue
        if name == "e2e20-cdp-neural-success.json" or d.get("outcome") == "success":
            return name, d
    return None, None


def harvest_success_artifacts():
    os.makedirs(DEST, exist_ok=True)
    for f in os.listdir(OUT):
        if f.startswith("e2e20") and (f.endswith(".json") or f.endswith(".png")):
            try:
                shutil.copy(f"{OUT}/{f}", f"{DEST}/{f}")
            except Exception:
                pass


def main():
    log("durability watcher started — snapshots every 30 min, success push the moment a marker lands")
    last_snapshot = 0
    while True:
        marker, data = check_success()
        if marker:
            log(f"SUCCESS MARKER: {marker} — harvesting full artifact set + pushing")
            harvest_success_artifacts()
            ok = git_push()
            with open(SUCCESS_FLAG, "w") as f:
                json.dump({"marker": marker, "pushed": ok, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
            log("done — exiting" + ("" if ok else " (PUSH FAILED — artifacts remain staged in the repo tree)"))
            return
        if time.time() - last_snapshot > 30 * 60:
            if snapshot():
                git_push()
            else:
                log("snapshot: unchanged")
            last_snapshot = time.time()
        time.sleep(60)


if __name__ == "__main__":
    main()
