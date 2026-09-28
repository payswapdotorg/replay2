#!/usr/bin/env python3
"""reentry_daemon.py — the turn-churn re-entry loop for the armed lanes.

The platform ends worker turns mid-flight (turn-churn). The queue_watches
detect completion only; continuation is the lead's job. This daemon automates
it: every 120s it reads the workers API; a lane whose DOM chars are static
for > STATIC_S (8 min) with no completion marker gets a continuation nudge
through dispatch_worker.py send. Nudges are rate-limited (>= 600s apart).
Exits when no armed lanes remain. Heartbeat: flags/reentry_heartbeat.
"""
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
PY = sys.executable
STATIC_S = 480        # static-DOM window before a nudge
NUDGE_GAP_S = 600     # min seconds between nudges per lane
POLL_S = 120
WORKERS_URL = "http://localhost:3000/api/workers"
LOG = os.path.join(BASE, "logs", "reentry-daemon.log")

NUDGE_TMPL = (
    "CONTINUE {name} — your turn ended mid-flight (the platform's turn-churn). "
    "RESUME your packet exactly where you stood (your written work survives in "
    "your sandbox). Keep going through the remaining steps, the guards, and the "
    "relay + report per your original packet. Reply with your first action, then keep working."
)


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def beat():
    try:
        open(os.path.join(FLAGS, "reentry_heartbeat"), "w").write(str(int(time.time() * 1000)))
    except Exception:
        pass


def armed_lanes():
    """name -> marker from the queue_watch specs (the armed lanes)."""
    out = {}
    for p in glob.glob(os.path.join(FLAGS, "queue_watch.spec.*")):
        try:
            d = json.load(open(p))
            out[d["name"]] = d.get("marker", "")
        except Exception:
            continue
    return out


def workers_state():
    try:
        with urllib.request.urlopen(WORKERS_URL, timeout=15) as r:
            d = json.load(r)
        return {w.get("name"): w for w in d.get("workers", [])}
    except Exception as e:
        log(f"workers API read failed: {e}")
        return {}


def send_nudge(name):
    path = os.path.join(FLAGS, f"{name}-nudge.txt")
    open(path, "w").write(NUDGE_TMPL.format(name=name.upper()))
    try:
        r = subprocess.run(
            [PY, os.path.join(BASE, "dispatch_worker.py"), "send", name, f"@{path}"],
            capture_output=True, text=True, timeout=240)
        tail = (r.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
        log(f"nudge {name}: {tail[0][:120]}")
        return "sent" in (r.stdout or "") or True
    except Exception as e:
        log(f"nudge {name} error: {e}")
        return False


def daemonize():
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    sys.stdout.flush(); sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    logfd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logfd, 1); os.dup2(logfd, 2)
    os.close(devnull); os.close(logfd)


def main():
    log(f"reentry daemon up (pid={os.getpid()})")
    state = {}  # name -> {chars, since, last_nudge}
    while True:
        beat()
        lanes = armed_lanes()
        if not lanes:
            log("no armed lanes — exiting")
            return 0
        ws = workers_state()
        for name in list(lanes):
            done_marker = os.path.join(FLAGS, f"{name}-complete.marker")
            if os.path.exists(done_marker):
                state.pop(name, None)
                continue
            w = ws.get(name)
            if not w:
                continue  # not in the panel (tab lost — queue_watch's lane)
            chars = w.get("chars") or 0
            st = state.setdefault(name, {"chars": chars, "since": time.time(), "last_nudge": 0})
            if chars != st["chars"]:
                st["chars"] = chars
                st["since"] = time.time()
                continue
            static_for = time.time() - st["since"]
            since_nudge = time.time() - st["last_nudge"]
            if static_for > STATIC_S and since_nudge > NUDGE_GAP_S:
                log(f"{name}: DOM static {int(static_for)}s (chars={chars}) — re-entry nudge")
                if send_nudge(name):
                    st["last_nudge"] = time.time()
                    st["since"] = time.time()  # restart the static window
        time.sleep(POLL_S)


if __name__ == "__main__":
    if "--foreground" in sys.argv:
        main()
    else:
        daemonize()
        main()
