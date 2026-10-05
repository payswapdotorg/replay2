#!/usr/bin/env python3
"""retry_lanes.py — outer retry loop for wave-3 lanes not owned by the watch.

wave3_spawn_watch owns unicom-w2-003 (its registry URL chain). This daemon
owns the lanes whose records were voided (watch skips them: "not in live"):
  - unicom-w1-003  (turn pipeline died server-side; re-dispatched fresh)
  - unicom-w3-003  (zombie record cleared; retrying)

Every ROUND_S: for each lane not yet landed:
  1. newest sent-record URL -> REAL liveness test (open chat URL in a tab;
     zombies redirect home instantly — the list API alone is NOT truth)
  2. if live: lane done (never touched again this run)
  3. else: void any blocking record, fire a create (fail-fast on capacity),
     re-test liveness; sleep between rounds.

MUST be launched via dfork_launch.py (the Bash tool reaps the whole tree
at call end — setsid/nohup do NOT escape it; see dfork_launch.py docstring).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import channel  # noqa: E402

LANES = ["unicom-w1-003", "unicom-w3-003"]
REGISTRY = os.path.join(HERE, "flags", "session_registry.jsonl")
LOG = os.path.join(HERE, "logs", "retry_lanes.log")
ROUND_S = 240
CREATE_TIMEOUT = 300
MAX_ROUNDS = 30


def log(msg):
    line = f"[retry-lanes {time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def _records():
    try:
        with open(REGISTRY) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except FileNotFoundError:
        return


def newest_sent_url(name):
    url = None
    for r in _records():
        if r.get("name") == name and r.get("sent") and r.get("url") \
                and r.get("action") != "void":
            url = r["url"]  # file order: newest wins
    return url


def record_blocks(name):
    blocked = False
    for r in _records():
        if r.get("name") != name:
            continue
        if r.get("action") == "void":
            blocked = False
        else:
            blocked = True
    return blocked


def chat_live_for_real(url):
    """Open the chat URL in a tab; a zombie redirects to home. Truth test."""
    try:
        tab = channel.new_tab(url)
        time.sleep(8)
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            href = c.eval("location.href", timeout=10) or ""
        finally:
            c.close()
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(
                "http://127.0.0.1:9222/json/close/" + tab["id"]), timeout=5).read()
        except Exception:
            pass
        cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
        if "/c/" in href and cid[:20] in href:
            return True
        log(f"liveness FAIL: {cid[:12]} -> landed on {href[:45]}")
        return False
    except Exception as e:
        log(f"liveness probe error: {e!r}")
        return False


def lane_done(name):
    url = newest_sent_url(name)
    return bool(url and chat_live_for_real(url))


def main():
    log(f"armed — lanes {LANES}, {ROUND_S}s rounds, max {MAX_ROUNDS}")
    pending = list(LANES)
    for rnd in range(1, MAX_ROUNDS + 1):
        if not pending:
            log("all lanes live — done")
            return 0
        still = []
        for name in pending:
            if lane_done(name):
                log(f"{name}: LIVE for real — retired from retry set")
                continue
            if record_blocks(name):
                subprocess.run([sys.executable, os.path.join(HERE, "dispatch_worker.py"),
                                "void", name, f"retry-lanes round {rnd}"],
                               capture_output=True, timeout=180, cwd=HERE)
            log(f"{name}: round {rnd} firing create")
            try:
                with open(os.path.join(HERE, "logs", f"dispatch-{name}.log"), "a") as lg:
                    subprocess.run([sys.executable, os.path.join(HERE, "dispatch_worker.py"),
                                    "create", name,
                                    os.path.join(HERE, "worker-prompts", f"{name}.md")],
                                   stdout=lg, stderr=subprocess.STDOUT,
                                   timeout=CREATE_TIMEOUT, cwd=HERE)
            except subprocess.TimeoutExpired:
                log(f"{name}: create timed out ({CREATE_TIMEOUT}s)")
            if lane_done(name):
                log(f"{name}: LIVE for real — retired from retry set")
                continue
            still.append(name)
        pending = still
        if pending:
            log(f"round {rnd} done; still pending: {pending} — sleeping {ROUND_S}s")
            time.sleep(ROUND_S)
    log(f"exhausted {MAX_ROUNDS} rounds; pending: {pending} — TL attention")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
