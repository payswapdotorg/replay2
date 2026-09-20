#!/usr/bin/env python3
"""backend_probe_watch.py — detached recovery detector for the generation wedge.

Context (2026-09-18): platform/account-level generation outage. All exits
tested (DE/GB/US) land prompts but never generate. The three prod workers
sit queued server-side. This watchdog runs backend_probe.py every 30 min:

  - verdict line appended to /tmp/backend_probe_watch.log
    (<utc-ts> HEALTHY|DOWN|TOOLFAIL [session])
  - first HEALTHY: appends an agent_outbox notice, touches
    flags/backend_recovered.txt, and keeps running (log only) so the
    resident can see sustained health, not a one-off.
  - never sends into worker sessions; each probe costs one tiny fresh
    session ('Reply with exactly: OK'), same instrument as backend_probe.

Exit codes n/a — runs forever until killed. Launch via
launch_backend_probe_watch.py (detached pattern, lesson 13).
"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(BASE, "backend_probe.py")
FLAGS = os.path.join(BASE, "flags")
LOG = "/tmp/backend_probe_watch.log"
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
MARKER = os.path.join(FLAGS, "backend_recovered.txt")
INTERVAL = 1800  # 30 min
PROBE_TIMEOUT = 300


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def run_probe():
    try:
        p = subprocess.run(
            [sys.executable, PROBE], capture_output=True, text=True,
            timeout=PROBE_TIMEOUT, cwd=BASE)
        out = (p.stdout or "") + (p.stderr or "")
        tail = out.strip().splitlines()[-1] if out.strip() else ""
        if "HEALTHY" in out:
            return "HEALTHY", tail
        if "DOWN" in out:
            return "DOWN", tail
        return "TOOLFAIL", tail[:120]
    except subprocess.TimeoutExpired:
        return "TOOLFAIL", "probe timeout"
    except Exception as e:
        return "TOOLFAIL", f"{type(e).__name__}: {e}"


def announce_recovery():
    import json
    notice = (
        "RECOVERY SIGNAL: the chat.z.ai generation backend just answered a "
        "fresh probe (assistant reply received). If the three queued workers "
        "(prod017/019/020) do not self-start within a few minutes, I will "
        "void + fresh re-dispatch them per the lesson-48 playbook. "
        "(automated notice from backend_probe_watch.py)"
    )
    entry = {"ts": int(time.time() * 1000), "from": "agent", "text": notice}
    with open(OUTBOX, "a") as f:
        f.write(json.dumps(entry) + "\n")
    with open(MARKER, "w") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + "\n")
    # 2026-09-19 OUTAGE-HOLD auto-lift: a HEALTHY probe means the generation
    # backend is back — remove the hold so the queue_watchers immediately
    # resume their full ladder (unstick / assault / fresh re-dispatch).
    try:
        os.remove(os.path.join(FLAGS, "outage_hold.txt"))
        log("OUTAGE-HOLD lifted (flags/outage_hold.txt removed)")
    except FileNotFoundError:
        pass


def main():
    log(f"watch start (every {INTERVAL}s, probe={PROBE})")
    recovered = os.path.exists(MARKER)
    while True:
        verdict, detail = run_probe()
        log(f"{verdict} {detail}")
        if verdict == "HEALTHY" and not recovered:
            recovered = True
            try:
                announce_recovery()
                log("recovery announced (outbox + marker)")
            except Exception as e:
                log(f"announce failed: {e}")
        try:
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
