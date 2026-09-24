#!/usr/bin/env python3
"""freeze_probe_watch.py — boot-prompt §16 protocol probe loop.

2026-09-23 22:20 UTC diagnosis: the 10.75h "Global limit reached" wedge
matches the personal-usage-limit family (§16): it gates GENERATION, not
sends, and EACH FAILED ATTEMPT APPEARS TO CONSUME/REFRESH the usage
window. The previous 30-min probe watch made 17 failed attempts in 9h —
likely continuously refreshing the block. Protocol now:

  (a) DONE — released the 12h-stale expired sandbox (settings/dashboard).
  (b) HARD FREEZE — no sends of any kind until FIRST_PROBE_UTC.
  (c) ONE probe per hour, never faster (doctrine: "never probe at a
      cadence faster than hourly under this limit").

Probe = backend_probe.py (tiny junk chat, never touches worker lanes).
On the FIRST HEALTHY verdict (exit 0): touch flags/backend_recovered.txt
(mtime-gated contract for endgame_recover.py, which then re-dispatches
both lanes + rewrites markers/lanes + lets the supervisor guard arm the
watches) + outbox notice, then exit 0.
TOOLING FAILURE (exit 2): retry in 10 min, does not count as an attempt
cycle against the hourly spacing (nothing landed server-side).

Usage: freeze_probe_watch.py   (detached via launch_detached.py)
"""
import os
import subprocess
import sys
import time

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
PROBE = os.path.join(BASE, "backend_probe.py")
MARKER = os.path.join(FLAGS, "backend_recovered.txt")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
LOG = "/tmp/freeze_probe_watch.log"
PY = "/home/z/.venv/bin/python3"
LAST_ATTEMPT = os.path.join(FLAGS, "freeze_probe_last.txt")
MIN_SPACING = 3300       # s — a restarted instance never probes sooner
                          # than ~55 min after the last landed attempt (§16)

# freeze until (UTC HH:MM) — hourly spacing after the last failed attempt
# (2026-09-24 12:26 DOWN probe, sandbox-reset #3 redeploy)
FIRST_PROBE_UTC = "13:30"
HOURLY = 3600


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def outbox(text):
    try:
        import json
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time() * 1000), "from": "agent",
                 "text": text}) + "\n")
    except OSError:
        pass


def wait_until(hhmm):
    """Sleep until today's (or tomorrow's) UTC HH:MM."""
    while True:
        now = time.gmtime()
        cur = f"{now.tm_hour:02d}:{now.tm_min:02d}"
        if cur >= hhmm:
            return
        # seconds until hhmm today
        h, m = map(int, hhmm.split(":"))
        target = h * 3600 + m * 60
        now_s = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
        time.sleep(min(900, max(1, target - now_s)))


def _note_attempt():
    """Persist the last probe epoch (restart-safe §16 spacing)."""
    try:
        with open(LAST_ATTEMPT, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def _wait_out_recent_attempt():
    """If a previous instance probed < MIN_SPACING ago, sleep the remainder
    so a supervisor restart never collapses the hourly cadence."""
    try:
        last = int(open(LAST_ATTEMPT).read().strip())
    except (OSError, ValueError):
        return
    remain = MIN_SPACING - (time.time() - last)
    if remain > 0:
        log(f"restart-safe spacing: last attempt {int(time.time() - last)}s "
            f"ago — holding {int(remain)}s before first probe (§16)")
        while remain > 0:
            time.sleep(min(900, remain))
            remain = MIN_SPACING - (time.time() - last)


def main():
    log(f"freeze active (§16b) — no sends until {FIRST_PROBE_UTC} UTC; "
        f"then ONE probe/hour max")
    wait_until(FIRST_PROBE_UTC)
    _wait_out_recent_attempt()
    log("freeze elapsed — starting hourly single-probe loop (§16c)")
    while True:
        try:
            r = subprocess.run([PY, PROBE], capture_output=True, text=True,
                               timeout=400)
            rc = r.returncode
            tail = (r.stdout or "").strip().splitlines()
            verdict = tail[-1] if tail else "(no output)"
        except subprocess.TimeoutExpired:
            rc, verdict = 2, "probe TIMEOUT"
        if rc == 0:
            log(f"HEALTHY — {verdict}")
            with open(MARKER, "w") as f:
                f.write(f"healthy at {time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            # lift the outage hold so queue_watch re-dispatch paths unblock
            # (2026-09-23 Task-96 patch, restored 2026-09-24 after reset #3;
            # committed so it survives the next reset)
            try:
                os.remove(os.path.join(FLAGS, "outage_hold.txt"))
                log("outage_hold.txt removed — queue_watch senders unblocked")
            except FileNotFoundError:
                pass
            outbox("[lead] HEALTHY probe! Generation capacity is back "
                   "(hourly-probe protocol, §16). Recovery chain firing: "
                   "both lanes re-dispatch fresh now; completion watches "
                   "will re-arm automatically.")
            log("marker written — endgame_recover takes over; exiting")
            return 0
        if rc == 2:
            log(f"TOOLFAIL — {verdict} (retry in 10 min, not an attempt)")
            time.sleep(600)
            continue
        _note_attempt()
        log(f"DOWN — {verdict}; next probe in 60 min (hourly max, §16c)")
        time.sleep(HOURLY)


if __name__ == "__main__":
    sys.exit(main())
