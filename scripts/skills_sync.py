#!/usr/bin/env python3
"""skills_sync.py — keeps the agent skills installed across sandbox recycles.

Why (2026-10-14/15 recycles #18–#21): the skills CLI install
(`npx -y skills add upstash/skills --global`) lands in $HOME (~/.agents,
~/.claude, ~/.config/crush) — every deep recycle resets $HOME to the
snapshot vintage, wiping post-snapshot installs. The upstash skill set
(14 skills) is a standing operator request; reinstalling it manually after
every recycle does not scale.

This daemon (supervised by supervisor.py, same pattern as vault_guard):
  - every cycle: count upstash-* skills under ~/.agents/skills
  - below expectation → run the non-interactive install (bounded 900s)
  - retry next cycle on failure; log outcomes only (never secrets)
  - flock single-instance; heartbeat flag for liveness checks

Run: dfork_launch.py <log> /home/z/.venv/bin/python3 scripts/skills_sync.py
"""
import fcntl
import os
import subprocess
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
LOCK = os.path.join(FLAGS, "skills_sync.lock")
HEARTBEAT = os.path.join(FLAGS, "skills_sync_heartbeat")

SKILLS_DIR = os.path.expanduser("~/.agents/skills")
EXPECTED = 14           # upstash skill families
CYCLE_S = 600           # check cadence
INSTALL_TIMEOUT_S = 900  # bounded install attempt
NPX = "/usr/bin/npx"


def log(msg):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, "skills_sync.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def upstash_skill_count():
    try:
        return len([d for d in os.listdir(SKILLS_DIR)
                    if d.startswith("upstash")])
    except Exception:
        return 0


def install():
    try:
        r = subprocess.run(
            [NPX, "-y", "skills", "add", "upstash/skills",
             "--global", "--agent", "*", "-y"],
            timeout=INSTALL_TIMEOUT_S, capture_output=True, text=True,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                 "GIT_TERMINAL_PROMPT": "0"})
        ok = r.returncode == 0
        log(f"install attempt: exit={r.returncode} "
            f"({'ok' if ok else 'failed — retry next cycle'})")
        return ok
    except subprocess.TimeoutExpired:
        log("install timed out — retry next cycle")
        return False
    except Exception as exc:
        log(f"install error ({exc!r}) — retry next cycle")
        return False


def main():
    os.makedirs(FLAGS, exist_ok=True)
    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another instance holds the lock
    log(f"skills_sync online (pid {os.getpid()}) — {CYCLE_S}s cycles, "
        f"expect {EXPECTED} upstash skills")
    while True:
        try:
            n = upstash_skill_count()
            if n >= EXPECTED:
                log(f"skills healthy ({n}/{EXPECTED})")
            else:
                log(f"skills missing ({n}/{EXPECTED}) — installing")
                install()
                log(f"post-install: {upstash_skill_count()}/{EXPECTED}")
        except Exception as exc:
            log(f"cycle error {exc!r} — continuing")
        try:
            with open(HEARTBEAT, "w") as f:
                f.write(str(int(time.time() * 1000)))
        except Exception:
            pass
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
