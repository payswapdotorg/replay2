#!/usr/bin/env python3
"""roadmap_watch.py — resident roadmap watcher (post-campaign holding pattern).

The campaign's engineering is complete (PA-00..PA-019; PRs #1..#52; main
a68cf94537d2 deployed + live-verified). The single open roadmap item is
PA-14 / ADCOS row 5, which is OPERATOR-BLOCKED (the four ADCOS_* production
keys must be issued out-of-band in ADCOS).

This daemon makes the TL's resident watch autonomous between check-ins.
Triggers (any -> agent_outbox notify + log; detection only, NEVER dispatch):

  1. MAIN-MOVE: origin/main of payswapdotorg/RoamLink advances beyond
     WATCH_SHA (a parallel session landed something, or an unexpected
     change reached main -> TL review needed).
  2. ADCOS-KEYS: ADCOS_* exports appear under ~/.secrets/ (the operator
     issued credentials -> PA-14 executable; the TL configures + runs
     RL-108 + re-acceptance in-session). Values are NEVER printed.
  3. SMOKE-RED: the RL-100 §6b synthetic smoke against the live alias
     flips red (regression alarm; includes the failing probe names).

Exit: MAX_HOURS (default 24h) -> exit 1 "TL review needed".
Launch idiom (lesson 147 — must orphan to PPID=1):
  bash -c 'cd /home/z/replay2/scripts && setsid nohup python3 \
      roadmap_watch.py < /dev/null > logs/roadmap_watch.log 2>&1 &'
"""
import json
import os
import re
import subprocess
import time

REPO = "/home/z/roamlink"
FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
SECRETS_DIR = os.path.expanduser("~/.secrets")
WATCH_SHA = "a68cf94537d247401c2368c8446fb300136680e6"
BASE_URL = "https://roamlink-ten.vercel.app"
CYCLE_S = 300          # 5 min
SMOKE_EVERY = 6        # smoke every 6th cycle (~30 min)
MAX_HOURS = float(os.environ.get("MAX_HOURS", "24"))

_run_tag = str(int(time.time()))[-6:]


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)


def outbox(text):
    """Post a message to the operator-visible console thread."""
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "text": text}) + "\n")
    except Exception as e:  # noqa: BLE001
        log("outbox write failed: %s" % e)


def main_sha():
    """origin/main via ls-remote (not API-rate-limited)."""
    try:
        out = subprocess.run(
            ["git", "-C", REPO, "ls-remote", "origin", "main"],
            capture_output=True, text=True, timeout=60)
        m = re.search(r"^([0-9a-f]{40})\s+refs/heads/main", out.stdout)
        return m.group(1) if m else None
    except Exception as e:  # noqa: BLE001
        log("ls-remote failed: %s" % e)
        return None


def adcos_key_names():
    """Names (never values) of ADCOS_* exports under ~/.secrets/*.sh|env."""
    names = set()
    try:
        for fn in os.listdir(SECRETS_DIR):
            path = os.path.join(SECRETS_DIR, fn)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        m = re.match(r"\s*(?:export\s+)?(ADCOS_[A-Z0-9_]+)\s*=", line)
                        if m:
                            names.add(m.group(1))
            except OSError:
                continue
    except OSError:
        return []
    return sorted(names)


def run_smoke():
    """RL-100 §6b smoke; returns (ok, detail)."""
    env = dict(os.environ)
    env["BASE_URL"] = BASE_URL
    env["SMOKE_TIMEOUT_MS"] = "15000"
    try:
        p = subprocess.run(
            ["node", "infra/deployment/smoke/run.mjs"],
            cwd=REPO, capture_output=True, text=True, timeout=180, env=env)
        tail = (p.stdout or "").strip().split("\n")[-1]
        if p.returncode == 0 and "0 failed" in tail:
            return True, tail
        fails = [l for l in (p.stdout or "").split("\n") if "[fail]" in l]
        return False, (tail or ("rc=%s" % p.returncode)) + \
            (" | " + "; ".join(fails[:3]) if fails else "")
    except Exception as e:  # noqa: BLE001
        return False, "smoke error: %s" % e


def main():
    global WATCH_SHA
    log("roadmap_watch armed: tag=%s watch_sha=%s cycle=%ss smoke_every=%d "
        "max=%.1fh" % (_run_tag, WATCH_SHA[:7], CYCLE_S, SMOKE_EVERY,
                       MAX_HOURS))
    log("state: engineering COMPLETE (PA-00..19, PRs #1-#52, main %s deployed;"
        " smoke 7/7 live-verified). Open item: PA-14/ADCOS row 5 "
        "(operator-blocked)." % WATCH_SHA[:7])
    deadline = time.time() + MAX_HOURS * 3600
    cycle = 0
    adcos_seen = False
    last_smoke_ok = True
    while time.time() < deadline:
        cycle += 1
        # 1. main-move
        sha = main_sha()
        if sha and sha != WATCH_SHA:
            log("MAIN-MOVE: %s -> %s" % (WATCH_SHA[:7], sha[:7]))
            outbox("ROADMAP WATCH: RoamLink main advanced %s -> %s — new "
                   "commits reached main outside this session's merges. TL "
                   "review needed (dispatch/review/verify before any next "
                   "step)." % (WATCH_SHA[:7], sha[:7]))
            WATCH_SHA = sha  # re-arm on the new head; TL reviews on check-in
        # 2. ADCOS keys
        keys = adcos_key_names()
        if keys and not adcos_seen:
            adcos_seen = True
            log("ADCOS-KEYS: %d key(s) present" % len(keys))
            outbox("ROADMAP WATCH: ADCOS credentials DETECTED in the vault "
                   "(%d key%s: %s) — PA-14 / ADCOS row 5 is now executable. "
                   "The TL will configure the production env, run the RL-108 "
                   "compatibility probe against the real endpoint, verify the "
                   "webhook path end-to-end, and re-run the journey suite + "
                   "demo acceptance." % (len(keys),
                                         "" if len(keys) == 1 else "s",
                                         ", ".join(keys)))
        elif not keys:
            adcos_seen = False
        # 3. smoke (paced)
        if cycle % SMOKE_EVERY == 0:
            ok, detail = run_smoke()
            log("smoke cycle %d: %s | %s" % (cycle, "OK" if ok else "RED",
                                             detail[:120]))
            if ok and not last_smoke_ok:
                outbox("ROADMAP WATCH: production smoke RECOVERED — %s" %
                       detail[:160])
            elif not ok and last_smoke_ok:
                outbox("ROADMAP WATCH: production smoke FLIPPED RED against "
                       "%s — %s — TL regression review needed." %
                       (BASE_URL, detail[:200]))
            last_smoke_ok = ok
        time.sleep(CYCLE_S)
    log("MAX_HOURS reached — exiting for TL review")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
