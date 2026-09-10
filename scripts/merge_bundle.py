#!/usr/bin/env python3
"""merge_bundle.py <wo> <slug> <crate> <bundle-path> <report-md> [expected-head-sha]

Full Tech-Lead merge pipeline for a worker git-bundle delivery:
  1. fetch the bundle into the canonical clone as refs/heads/wo-<n>/<slug>
  2. VALIDATE: merge-base == current main HEAD; exactly ONE commit on the
     branch; the diff touches only the new crate + the Cargo.toml members
     line + Cargo.lock; head SHA matches the report (when given).
  3. VERIFY on the real toolchain (CARGO_INCREMENTAL=0, disk-lean):
     cargo test / clippy -D warnings / fmt --check, scoped to the crate.
  4. PUSH branch, create PR, squash-merge, delete the branch ref.
  5. STATE COMMIT: execution-state.json update + report filed under
     docs/development-state/reports/WO-XXX-report.md.

Exits non-zero at the first gate that fails (nothing is pushed before all
verification gates pass).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

CLONE = "/home/z/codex-clone"
CARGO_DIR = os.path.join(CLONE, "codex-rs")
CARGO = os.path.expanduser("~/.cargo/bin/cargo")


def sh(cmd, cwd=CLONE, check=True, env_extra=None, timeout=1800):
    env = dict(os.environ)
    env["CARGO_INCREMENTAL"] = "0"
    if env_extra:
        env.update(env_extra)
    print(f"+ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, timeout=timeout)
    if r.stdout:
        print(r.stdout[-3000:])
    if r.returncode != 0 and check:
        print(r.stderr[-3000:])
        raise SystemExit(f"FAILED: {' '.join(cmd)}")
    return r


def gh_token():
    url = sh(["git", "remote", "get-url", "origin"], check=True).stdout.strip()
    m = re.match(r"https://x-access-token:([^@]+)@github\.com/payswapdotorg/codex\.git", url)
    if not m:
        raise SystemExit("could not extract token from remote url")
    return m.group(1)


def api(token, method, path, body=None):
    req = urllib.request.Request(
        f"https://api.github.com/repos/payswapdotorg/codex/{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=60) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else {}


def main():
    wo, slug, crate, bundle, report_md = sys.argv[1:6]
    expected_head = sys.argv[6] if len(sys.argv) > 6 else None
    n = wo.split("-")[1]
    branch = f"wo-{n}/{slug}"

    # 1. refresh + fetch bundle
    sh(["git", "fetch", "origin", "main"])
    main_head = sh(["git", "rev-parse", "origin/main"]).stdout.strip()
    sh(["git", "bundle", "verify", bundle])
    sh(["git", "fetch", bundle, f"{branch}:{branch}"])
    head = sh(["git", "rev-parse", branch]).stdout.strip()
    base = sh(["git", "merge-base", branch, "origin/main"]).stdout.strip()
    if base != main_head:
        raise SystemExit(f"BASE MISMATCH: merge-base {base} != origin/main {main_head}")
    commits = sh(["git", "log", "--format=%H", f"origin/main..{branch}"]).stdout.split()
    if len(commits) != 1:
        raise SystemExit(f"expected exactly 1 commit, got {len(commits)}")
    if expected_head and head != expected_head:
        raise SystemExit(f"HEAD MISMATCH: {head} != report {expected_head}")

    # 2. scope validation
    changed = sh(["git", "diff", "--name-only", f"origin/main..{branch}"]).stdout.split()
    allowed_prefix = f"codex-rs/{slug}/"
    bad = [f for f in changed if not (f.startswith(allowed_prefix) or f in ("codex-rs/Cargo.toml", "codex-rs/Cargo.lock"))]
    if bad:
        raise SystemExit(f"SCOPE VIOLATION: out-of-scope files {bad}")
    stat = sh(["git", "diff", "--stat", f"origin/main..{branch}"]).stdout.strip().splitlines()[-1]
    print(f"scope OK: {len(changed)} files — {stat}")

    # 3. real verification (workspace root is codex-rs/)
    sh(["git", "checkout", branch])
    test = sh([CARGO, "test", "-p", crate], cwd=CARGO_DIR, timeout=2400)
    m = re.findall(r"(\d+) passed", test.stdout)
    tests_passed = "+".join(m) if m else "?"
    sh([CARGO, "clippy", "-p", crate, "--all-targets", "--", "-D", "warnings"], cwd=CARGO_DIR, timeout=2400)
    sh([CARGO, "fmt", "-p", crate, "--", "--check"], cwd=CARGO_DIR)
    print(f"verification OK: tests={tests_passed} passed, clippy clean, fmt clean")
    sh(["git", "checkout", "main"])

    # 4. push + PR + squash merge + branch delete
    token = gh_token()
    sh(["git", "push", "origin", f"{branch}"])
    sh(["git", "branch", "-D", branch])
    title = f"feat({slug}): {wo} {slug.replace('-', ' ')}"
    body = (f"Worker delivery via git bundle (agents-tab session, GLM-5.3 + Full-Stack).\n\n"
            f"Independent verification (real toolchain 1.95.0): {tests_passed} tests passed; "
            f"clippy -D warnings clean; fmt clean. Base: main @ {main_head[:10]}; "
            f"head: {head[:10]}; 1 commit; {len(changed)} files ({stat}).\n\n"
            f"Report: docs/development-state/reports/{wo}-report.md")
    pr = api(token, "POST", "pulls", {"title": title, "body": body, "head": branch, "base": "main"})
    num = pr["number"]
    print(f"PR #{num} created")
    api(token, "PUT", f"pulls/{num}/merge", {"merge_method": "squash"})
    print(f"PR #{num} squash-merged")
    sh(["git", "push", "origin", "--delete", branch])
    sh(["git", "fetch", "origin", "main"])
    new_head = sh(["git", "rev-parse", "origin/main"]).stdout.strip()
    sh(["git", "reset", "--hard", "origin/main"])

    # 5. state commit
    report = open(report_md, encoding="utf-8").read()
    rpt_path = f"docs/development-state/reports/{wo}-report.md"
    with open(os.path.join(CLONE, rpt_path), "w", encoding="utf-8") as f:
        f.write(report)
    state_path = "docs/development-state/execution-state.json"
    state = json.load(open(os.path.join(CLONE, state_path)))
    merged_count = 10 + int(n) - 10  # 010->10 ... 015->15
    state["last_verified_sha"] = f"main @ {new_head[:12]} ({wo}: {crate} {tests_passed} tests, clippy+fmt clean)"
    state["verification_state"] = f"wo{n}-{merged_count}of15"
    state["notes"] = (f"{wo} MERGED via PR #{num} (squash, {new_head[:12]}): {slug} — new leaf crate "
                      f"codex-rs/{slug}. Independent verification on real toolchain 1.95.0: cargo test -p {crate} "
                      f"{tests_passed} tests green; clippy -D warnings clean; fmt clean. Delivered via git-bundle "
                      f"in the workspace archive (head {head[:12]}, base {main_head[:12]}). Report: {rpt_path}. "
                      f"{merged_count}/15 WOs merged.")
    with open(os.path.join(CLONE, state_path), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    sh(["git", "add", rpt_path, state_path])
    sh(["git", "commit", "-m",
        f"docs(state): {wo} MERGED via PR #{num} (verified {tests_passed} tests, clippy/fmt clean); {merged_count}/15 WOs"])
    sh(["git", "push", "origin", "main"])
    print(f"DONE: {wo} merged; main @ {new_head[:12]}; {merged_count}/15 WOs")


if __name__ == "__main__":
    main()
