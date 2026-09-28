#!/usr/bin/env python3
"""post_outage_recovery.py — the outage-hold handshake's missing half.

2026-09-28 16:3x UTC context: generation outage (backend_probe DOWN; r37's
revival send rendered but rolled back server-side — rejected turns do NOT
commit the user message, so the revival MUST be re-sent after recovery).
r38a/r38b voided (queued-zombies). Outage hold active; backend_probe_watch
polling every 30 min and will touch flags/backend_recovered.txt on first
HEALTHY.

This daemon (run detached; supervisor keeps it alive via spec below):
  1. waits for flags/backend_recovered.txt (consumes the marker);
  2. lifts flags/outage_hold.txt (watchers resume their full ladders);
  3. re-sends the r37 revival directive (dispatch_worker.py send) and
     verifies the server-side commit (chats-API msgs grows) — bounded
     retries; a failed verification leaves the watcher ladder in charge;
  4. re-creates r38a + r38b from their original prompt files (staggered;
     create() runs the full verified assault loop incl. capacity modals);
  5. starts a queue_watch.py per new session (it writes its own spec, the
     supervisor adopts it);
  6. logs a heartbeat to flags/post_outage_recovery.heartbeat every cycle.

Never clicks Cancel on GLM-5.3 capacity (create() owns that policy). Never
waits a cooldown: this daemon's wait is the DESIGNED outage-hold, released
the moment the probe reports HEALTHY.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
FLAGS = os.path.join(BASE, "flags")
MARKER = os.path.join(FLAGS, "backend_recovered.txt")
HOLD = os.path.join(FLAGS, "outage_hold.txt")
HB = os.path.join(FLAGS, "post_outage_recovery.heartbeat")
LOG = os.path.join(BASE, "logs", "post_outage_recovery.log")
CYCLE = 60
SEND_RETRIES = 4
R37_CID = "f149e0b2-9de1-4b11-814c-434b254932d1"
R37_REVIVAL = os.path.join(BASE, "worker-prompts", "r37-revival.md")
R38A_PROMPT = os.path.join(BASE, "worker-prompts", "r38a-upload.md")
R38B_PROMPT = os.path.join(BASE, "worker-prompts", "r38b-studio.md")


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"[{stamp}] {line}\n")
    print(f"[{stamp}] {line}", flush=True)


def run(cmd, timeout=280):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=BASE)


def r37_server_msgs():
    """Server-side message count for r37's chat (chats-API truth)."""
    try:
        sys.path.insert(0, BASE)
        import probe_chat
        pr = run([sys.executable, os.path.join(BASE, "probe_chat.py"), R37_CID, "x"], timeout=90)
        d = json.loads(pr.stdout.strip().split("\n")[-1])
        return int(d.get("msgs") or 0)
    except Exception as e:
        log(f"r37 probe error: {type(e).__name__}: {e}")
        return -1


def send_revival():
    """Re-send the r37 revival; ground truth = server-side msgs growth."""
    before = r37_server_msgs()
    if before < 0:
        return False
    for attempt in range(1, SEND_RETRIES + 1):
        r = run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                 "send", "r37", "@" + R37_REVIVAL])
        out = (r.stdout or "") + (r.stderr or "")
        log(f"r37 revival send attempt {attempt}: rc={r.returncode} :: {out.strip()[-200:]}")
        time.sleep(20)
        after = r37_server_msgs()
        log(f"r37 server msgs: {before} -> {after}")
        if after > before:
            log("r37 revival COMMITTED server-side — the turn will fire")
            return True
        # the send may have staged: the next attempt re-fires the composer
    log("r37 revival NOT committed after bounded retries — watcher ladder owns it now")
    return False


WEBFLIX = "/home/z/WebFlix"
BRANCH_BY_NAME = {"r38a": "wfx/r38a/upload", "r38b": "wfx/r38b/studio"}


def duplicate_delivered(name):
    """Parallel-lead guard (lesson 201): if the work item's branch already
    exists on the WebFlix remote (e.g. the TL-Station ali10 duplicate
    delivered first), do NOT double-dispatch — leave it for Lead review."""
    br = BRANCH_BY_NAME.get(name)
    if not br:
        return False
    try:
        run(["git", "-C", WEBFLIX, "fetch", "origin", "--quiet"], timeout=120)
        rr = run(["git", "-C", WEBFLIX, "rev-parse", "--verify", f"origin/{br}"], timeout=30)
        return rr.returncode == 0
    except Exception as e:
        log(f"branch check for {name} failed: {e}")
        return False  # unverifiable = proceed (the normal path)


def create_worker(name, prompt):
    if duplicate_delivered(name):
        log(f"SKIP create {name}: branch {BRANCH_BY_NAME[name]} already on the remote "
            "(parallel-lead duplicate delivered?) — Lead review owns it")
        return None
    r = run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
             "create", name, prompt], timeout=580)
    out = (r.stdout or "") + (r.stderr or "")
    log(f"create {name}: rc={r.returncode} :: {out.strip()[-300:]}")
    # find the new tab prefix from the registry (latest record for name)
    try:
        import dispatch_worker as dw
        rec = dw._find(name)
        if rec and rec.get("tab_id"):
            return rec["tab_id"][:8]
    except Exception as e:
        log(f"registry lookup for {name} failed: {e}")
    return None


def start_watcher(name, tab_prefix, marker):
    if not tab_prefix:
        log(f"cannot start watcher for {name}: no tab prefix")
        return
    subprocess.Popen(
        [sys.executable, os.path.join(BASE, "queue_watch.py"), name, tab_prefix, marker],
        stdout=open(os.path.join(BASE, "logs", "queue-watch.log"), "a"),
        stderr=subprocess.STDOUT)
    log(f"queue_watch started: {name} tab={tab_prefix} marker='{marker}'")


def main():
    log("post-outage recovery daemon online — waiting for backend_recovered.txt")
    while True:
        try:
            with open(HB, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
            if not os.path.exists(MARKER):
                time.sleep(CYCLE)
                continue
            # HEALTHY sighted — consume the marker
            try:
                os.remove(MARKER)
            except Exception:
                pass
            log("BACKEND RECOVERED marker consumed — lifting outage hold")
            try:
                os.remove(HOLD)
                log("outage_hold.txt removed (watchers resume full ladders)")
            except FileNotFoundError:
                log("outage hold already lifted")
            # 1) r37 revival first (protect the M1-M3 work from any assault)
            send_revival()
            # 2) re-create r38a + r38b (staggered)
            tab_a = create_worker("r38a", R38A_PROMPT)
            time.sleep(30)
            tab_b = create_worker("r38b", R38B_PROMPT)
            # 3) watchers for the new sessions
            start_watcher("r38a", tab_a, "R38A COMPLETION REPORT")
            start_watcher("r38b", tab_b, "R38B COMPLETION REPORT")
            log("post-outage recovery COMPLETE — normal wave cadence resumes")
            return  # one-shot: its job is done; the wave loop + watchers own the rest
        except Exception as e:
            log(f"cycle error: {type(e).__name__}: {e}")
            time.sleep(CYCLE)


if __name__ == "__main__":
    main()
