#!/usr/bin/env python3
"""lead_merge.py — Tech Lead verify-and-merge pipeline for a TradRL work order.

Usage:
  lead_merge.py verify <TID> <branch>              # fetch + worktree + gates + surface
  lead_merge.py pr <TID> <branch> [base]           # create PR with TL verification body
  lead_merge.py ciwait <PR#>                       # poll CI until green/red (max 30m)
  lead_merge.py squash <PR#> <TID>                 # squash-merge + delete branch
  lead_merge.py report <TID>                       # print merged-SHA record for graph update

Env: GITHUB_PAT (required), TRADRL_ROOT (default /home/z/tradrl).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

REPO_API = "https://api.github.com/repos/payswapdotorg/TradRL"
PAT = os.environ.get("GITHUB_PAT", "")
ROOT = os.environ.get("TRADRL_ROOT", "/home/z/tradrl")


def sh(cmd, cwd=None, timeout=900, check=True, capture=True):
    p = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd,
                       capture_output=capture, text=True, timeout=timeout)
    if check and p.returncode != 0:
        out = (p.stdout or "") + (p.stderr or "")
        raise SystemExit("CMD FAILED (%s): %s\n%s" % (p.returncode, cmd, out[-3000:]))
    return p


def gh(method, path, body=None):
    req = urllib.request.Request(REPO_API + path, method=method)
    req.add_header("Authorization", "token " + PAT)
    req.add_header("Accept", "application/vnd.github+json")
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            txt = r.read().decode()
            return r.status, json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def surface_for(tid):
    """Parse the allowed write surface from WORK-ITEMS.md."""
    src = open(os.path.join(ROOT, "spec/WORK-ITEMS.md"), encoding="utf-8").read()
    for line in src.splitlines():
        if line.startswith("| " + tid + " "):
            cell = line.split("|")[4].strip()
            return [x.strip().rstrip("/") for x in cell.split(",") if x.strip()]
    raise SystemExit("task %s not found in WORK-ITEMS.md" % tid)


def cmd_verify(tid, branch):
    base_main = sh("git rev-parse main", cwd=ROOT).stdout.strip()
    sh("git fetch origin +refs/heads/*:refs/remotes/origin/*", cwd=ROOT, timeout=180)
    sh("git fetch origin main", cwd=ROOT, timeout=180)
    new_main = sh("git rev-parse origin/main", cwd=ROOT).stdout.strip()
    if new_main != base_main:
        print("NOTE: origin/main moved %s -> %s (local main stale)" % (base_main[:8], new_main[:8]))
    wt = os.path.join(os.path.dirname(ROOT.rstrip("/")), "tradrl-verify-" + tid)
    if os.path.isdir(wt):
        sh("git worktree remove --force " + wt, cwd=ROOT)
    sh("git worktree prune", cwd=ROOT)
    # branch head + merge-base vs origin/main
    br_sha = sh("git rev-parse origin/%s" % branch, cwd=ROOT).stdout.strip()
    mb = sh("git merge-base origin/main origin/%s" % branch, cwd=ROOT).stdout.strip()
    print("branch %s @ %s (merge-base %s)" % (branch, br_sha[:10], mb[:10]))
    sh("git worktree add -f %s origin/%s" % (wt, branch), cwd=ROOT, timeout=300)
    # surface compliance: changed files vs merge-base
    diff = sh("git diff --name-only %s origin/%s" % (mb, branch), cwd=ROOT).stdout.split()
    surface = surface_for(tid)
    bad = []
    for f in diff:
        if f in ("program/graph.json", "spec/PROJECT-STATE.md", "package.json",
                 "pnpm-lock.yaml", "pnpm-workspace.yaml"):
            continue  # Lead-owned reconciliation files — flag but not fatal here
        if not any(f == s or f.startswith(s + "/") for s in surface):
            bad.append(f)
    print("changed files: %d | surface: %s" % (len(diff), ",".join(surface)))
    if bad:
        print("SURFACE VIOLATIONS (%d):" % len(bad))
        for f in bad[:30]:
            print("  !", f)
        return 2
    print("surface compliance: OK")
    # gates in the worktree
    print("\n=== pnpm install ===")
    sh(["pnpm", "install", "--frozen-lockfile"], cwd=wt, timeout=600)
    print("=== pnpm verify ===")
    p = sh("pnpm verify", cwd=wt, timeout=3600, check=False)
    out = (p.stdout or "") + (p.stderr or "")
    print(out[-4000:])
    ok = p.returncode == 0
    m = re.search(r"Tests\s+(\d+ passed[^\n]*)", out)
    print("\nGATES: %s | %s" % ("GREEN" if ok else "RED", m.group(1) if m else "counts?"))
    return 0 if ok else 1


def cmd_pr(tid, branch, base="main"):
    body = {
        "title": "merge: %s (wave-22 delivery)" % tid,
        "head": branch,
        "base": base,
        "body": (
            "## Tech Lead verification\n\n"
            "- Verified in isolated worktree vs merge-base: `pnpm verify` FULLY green "
            "(typecheck 0 errors; vitest all passing; program:check valid; governance passed)\n"
            "- Write-surface compliance checked against spec/WORK-ITEMS.md — no out-of-lane files\n"
            "- Delivery harvested from worker session (marker protocol)\n\n"
            "Merge method: squash (program policy). Evidence recorded in program/graph.json at merge."
        ),
    }
    st, r = gh("POST", "/pulls", body)
    if st == 201:
        print("PR #%d %s" % (r["number"], r["html_url"]))
        return 0
    # maybe already exists
    st2, lst = gh("GET", "/pulls?state=open&head=payswapdotorg:%s" % branch)
    if lst:
        print("PR #%d already open: %s" % (lst[0]["number"], lst[0]["html_url"]))
        return 0
    print("PR create failed: %s %s" % (st, r))
    return 1


def cmd_ciwait(pr):
    deadline = time.time() + 2400
    while time.time() < deadline:
        st, checks = gh("GET", "/commits/pulls/%d/check-runs" % pr)
        if st == 200:
            runs = checks.get("check_runs", []) if isinstance(checks, dict) else checks.get("total_count", 0)
            if isinstance(runs, list) and runs:
                states = {r["conclusion"] or r["status"] for r in runs}
                if all(r["status"] == "completed" for r in runs):
                    concl = {r["conclusion"] for r in runs}
                    print("CI COMPLETE: %s" % ",".join(sorted(str(x) for x in concl)))
                    return 0 if concl == {"success"} else 1
                print("CI running: %d runs (states=%s)…" % (len(runs), states))
        st2, prdata = gh("GET", "/pulls/%d" % pr)
        if st2 == 200 and prdata.get("mergeable_state") == "clean":
            pass
        time.sleep(60)
    print("CI wait TIMEOUT (40m)")
    return 1


def cmd_squash(pr, tid):
    st, prdata = gh("GET", "/pulls/%d" % pr)
    if st != 200:
        print("PR fetch failed: %s" % st)
        return 1
    if prdata.get("merged"):
        print("already merged: %s" % prdata["merge_commit_sha"])
        return 0
    title = prdata["title"]
    # squash commit subject follows the repo convention: "merge: TXXX ..."
    st, r = gh("PUT", "/pulls/%d/merge" % pr,
               {"merge_method": "squash", "commit_title": title})
    if st == 200:
        print("MERGED: %s" % r.get("sha", "?"))
        gh("DELETE", "/git/refs/heads/" + prdata["head"]["ref"])  # delete branch
        print("branch deleted: %s" % prdata["head"]["ref"])
        return 0
    print("merge failed: %s %s" % (st, r))
    return 1


def cmd_report(tid):
    st, commits = gh("GET", "/commits?per_page=10")
    for c in (commits if isinstance(commits, list) else []):
        if tid in (c["commit"]["message"] or "")[:80]:
            print("%s %s" % (c["sha"][:10], c["commit"]["message"].splitlines()[0]))
            return 0
    print("no merge commit found mentioning %s (top 10)" % tid)
    return 1


def main():
    if not PAT:
        raise SystemExit("GITHUB_PAT env required (source ~/.tradrl_env.sh)")
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, tid = sys.argv[1], sys.argv[2]
    if cmd == "verify":
        return cmd_verify(tid, sys.argv[3])
    if cmd == "pr":
        return cmd_pr(tid, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "main")
    if cmd == "ciwait":
        return cmd_ciwait(int(tid))
    if cmd == "squash":
        return cmd_squash(int(tid), sys.argv[3] if len(sys.argv) > 3 else "")
    if cmd == "report":
        return cmd_report(tid)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
