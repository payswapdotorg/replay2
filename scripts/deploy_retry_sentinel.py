#!/usr/bin/env python3
"""deploy_retry_sentinel.py — Vercel quota-window retry loop (2026-09-22).

The free-tier api-deployments-free-per-day quota (100/day) was exhausted
by yesterday's deploy cadence; the redeploy of the final lineage is the
PROD-015 critical path. Yesterday's deployments age out of the rolling
window progressively. This sentinel retries the production deploy every
cycle until it lands:

  - attempt: bunx vercel deploy --prod --yes (VERCEL_TOKEN from env.sh)
  - success signature: a vercel.app URL in the output tail
  - on success: write flags/deploy-final.marker + outbox post + exit 0
  - on burnout: exit 3

Usage: deploy_retry_sentinel.py [--every 1500] [--max-hours 20]
"""
import json, os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REPO = "/home/z/AISE"

def log(line):
    print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)

def post_outbox(text):
    rec = {"ts": int(time.time()*1000), "text": text}
    with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")

def main():
    args = sys.argv[1:]
    every, max_h = 1500, 20
    if "--every" in args:
        i = args.index("--every"); every = int(args[i+1]); del args[i:i+2]
    if "--max-hours" in args:
        i = args.index("--max-hours"); max_h = float(args[i+1]); del args[i:i+2]
    deadline = time.time() + max_h*3600
    attempt = 0
    env = dict(os.environ)
    # source the token
    try:
        for line in open("/home/z/.secrets/env.sh"):
            line = line.strip()
            if line.startswith("export VERCEL_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                env["VERCEL_TOKEN"] = tok
    except Exception as e:
        log(f"token load err: {e}"); return 3
    while time.time() < deadline:
        attempt += 1
        # 2026-09-22 guard (pass-15 lesson: this daemon once deployed a dirty
        # mid-merge tree): only ever deploy a CLEAN main working tree.
        try:
            st = subprocess.run(["git", "-C", REPO, "status", "--porcelain"],
                                capture_output=True, text=True, timeout=30)
            br = subprocess.run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=30)
            if st.stdout.strip() or br.stdout.strip() != "main":
                log(f"attempt {attempt}: repo not clean-on-main (branch={br.stdout.strip()!r}, dirty={len(st.stdout.splitlines())}) — sleeping {every}s")
                time.sleep(every)
                continue
        except Exception as e:
            log(f"attempt {attempt}: git guard err {str(e)[:80]} — sleeping")
            time.sleep(every)
            continue
        try:
            r = subprocess.run(["bunx", "vercel", "deploy", "--prod", "--yes"],
                               capture_output=True, text=True, timeout=560,
                               cwd=REPO, env=env)
            out = (r.stdout or "") + (r.stderr or "")
            tail = out.strip().splitlines()[-3:] if out.strip() else []
            if "api-deployments-free-per-day" in out:
                log(f"attempt {attempt}: quota still limited — sleeping {every}s")
            elif "vercel.app" in out and ("Production" in out or r.returncode == 0):
                url = next((l.strip() for l in out.splitlines() if "vercel.app" in l and "https" in l), "?")
                log(f"attempt {attempt}: DEPLOYED — {url}")
                open(os.path.join(FLAGS, "deploy-final.marker"), "w").write(
                    f"{url} {int(time.time())}\n")
                post_outbox(f"FINAL REDEPLOY LANDED: {url} — PROD-015 Gate F + deployed-check re-verification now unblocked (Lead executing)")
                return 0
            else:
                log(f"attempt {attempt}: rc={r.returncode} tail={' | '.join(tail)[:220]}")
                # a hard failure that is NOT quota — keep retrying a few times anyway
        except subprocess.TimeoutExpired:
            log(f"attempt {attempt}: deploy timed out (560s) — retrying")
        except Exception as e:
            log(f"attempt {attempt}: err {str(e)[:120]}")
        time.sleep(every)
    log("burnout: quota window never freed within max-hours")
    return 3

if __name__ == "__main__":
    raise SystemExit(main())
