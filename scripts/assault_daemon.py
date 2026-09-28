#!/usr/bin/env python3
"""assault_daemon.py <name> <prompt-file> — the persisted-packet assault loop.

Double-fork daemonized (immune to CLI process-group kills). Every cycle:
  1. If the registry already shows <name> sent=true (create action) → exit 0.
  2. Run dispatch_worker.py create <name> <prompt-file> (its own assault
     handles the capacity popup rounds; each invocation ≈ 13 min max).
  3. Sleep 90s, re-check, repeat — capacity frees when a generating lane's
     turn ends; the packet fires then.

Self-limits: 4 hours wall-clock. Heartbeat: flags/<name>_assault_heartbeat.
Log: logs/<name>-assault.log
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
PY = sys.executable
DEADLINE_H = 4.0


def log(path, msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def landed(name):
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except Exception:
                    continue
                if row.get("name") == name and row.get("sent") is True and \
                        row.get("kind", "create") == "create":
                    return True
    except FileNotFoundError:
        pass
    return False


def beat(name):
    try:
        with open(os.path.join(FLAGS, f"{name}_assault_heartbeat"), "w") as f:
            f.write(str(int(time.time() * 1000)))
    except Exception:
        pass


def daemonize(logpath):
    if os.fork() > 0:
        sys.exit(0)  # parent exits
    os.setsid()
    if os.fork() > 0:
        os._exit(0)  # session leader exits; grandchild orphaned to init
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    logfd = os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    os.close(devnull)
    os.close(logfd)


def main(name, prompt):
    logpath = os.path.join(LOGDIR, f"{name}-assault.log")
    start = time.time()
    log(logpath, f"daemon up (pid={os.getpid()}) — assaulting {name} until landed or {DEADLINE_H}h")
    cycle = 0
    while True:
        beat(name)
        if landed(name):
            log(logpath, f"LANDED (cycle {cycle}) — registry shows {name} sent=true; exiting")
            return 0
        if (time.time() - start) > DEADLINE_H * 3600:
            log(logpath, f"deadline ({DEADLINE_H}h) reached without landing — exiting (packet stays staged)")
            return 1
        cycle += 1
        log(logpath, f"cycle {cycle}: dispatch attempt (capacity assault inside)")
        try:
            r = subprocess.run(
                [PY, os.path.join(BASE, "dispatch_worker.py"), "create", name, prompt],
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                timeout=16 * 60,
            )
            log(logpath, f"cycle {cycle}: dispatcher rc={r.returncode}")
        except subprocess.TimeoutExpired:
            log(logpath, f"cycle {cycle}: dispatcher timed out (16m) — re-looping")
        except Exception as e:  # noqa: BLE001
            log(logpath, f"cycle {cycle}: dispatcher error: {e}")
        time.sleep(90)


if __name__ == "__main__":
    if len(sys.argv) < 3 or "--foreground" in sys.argv[3:]:
        print("usage: assault_daemon.py <name> <prompt-file> [--foreground]")
        sys.exit(2)
    name, prompt = sys.argv[1], sys.argv[2]
    os.makedirs(FLAGS, exist_ok=True)
    os.makedirs(LOGDIR, exist_ok=True)
    if len(sys.argv) < 4 or sys.argv[3] != "--foreground":
        daemonize(os.path.join(LOGDIR, f"{name}-assault.log"))
    main(name, os.path.abspath(prompt))
