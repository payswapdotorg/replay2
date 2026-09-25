#!/usr/bin/env python3
"""r0_redisp_loop.py — patient Wave R0 completion loop (post002/post003).

CONTEXT (2026-09-25 12:30Z): post001 landed + COMPLETE. post002/post003
exhausted the r0_login_sentinel's 3-attempt passes against the GLM-5.3
capacity wall (the platform HIDES GLM-5.3 in the model menu under capacity
pressure; it flickers — one post003 assault round verified the model, the
next round it was gone). This loop takes over when the sentinel exits and
keeps dispatching, ONE create at a time (no orphan-create crossfire — the
sentinel's 300s registry window orphaned creates that kept assaulting in
parallel, interleaving logs and churning tabs):

  every round:
    - yield while r0_login_sentinel is still running (lock pid alive);
    - re-entry law: registry append-order truth (landed = sent + /c/ url,
      no later void/failed/done) — a landed session is NEVER re-dispatched;
    - workspace gate (<3 active; dash_sandbox_release backstop);
    - dispatch_worker create (full assault machinery, 12 rounds INSIDE one
      process, waited to EXIT — bounded orphans to zero);
    - on landing: arm one queue_watch per session (COMPLETION REPORT
      marker, supervisor-resurrectable via spec) + outbox notice.

Exit: both sessions landed (outbox Wave-R0-complete), or the 8h window
burns (outbox stand-down; the lead re-arms on next wake).

Usage:  python3 scripts/r0_redisp_loop.py   (detached; one instance only)
Log:    scripts/logs/r0_redisp.log   Heartbeat: flags/r0_redisp_heartbeat
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import channel          # noqa: E402
import r0_login_sentinel as rs  # noqa: E402  (landed/pre_clean/gate reuse)

TAG = "r0-redisp"
LOG_PATH = os.path.join(BASE, "logs", "r0_redisp.log")
HEARTBEAT = os.path.join(BASE, "flags", "r0_redisp_heartbeat")
LOCK = os.path.join(BASE, "flags", "r0_redisp.lock")
OUTBOX = os.path.join(BASE, "flags", "agent_outbox.jsonl")

QUEUE = [
    ("post002", "POST002.md", "POST-002 COMPLETION REPORT"),
    ("post003", "POST003.md", "POST-003 COMPLETION REPORT"),
]

ROUND_SLEEP = 240          # between rounds
CREATE_TIMEOUT = 1500      # one create = up to 12 assault rounds (~20 min)
REGISTRY_WAIT = 240        # chat_id poll after create exit
MAX_RUNTIME = 8 * 3600

LOG = open(LOG_PATH, "a", buffering=1)


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", file=LOG, flush=True)


def beat():
    with open(HEARTBEAT, "w") as f:
        f.write(str(time.time()))


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time() * 1000), "from": "agent", "text": text}
            ) + "\n")
    except OSError:
        pass


def sentinel_running():
    """The login sentinel's own lock + pid check (yield while it works)."""
    try:
        pid = int(open(rs.LOCK).read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"r0_login_sentinel" in f.read()
    except (OSError, ValueError):
        return False


def registry_chat_id(name, timeout_secs):
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        beat()
        try:
            with open(rs.REGISTRY) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("name") != name or not d.get("sent"):
                        continue
                    if d.get("chat_id"):
                        return d["chat_id"]
                    url = d.get("url") or ""
                    if "/c/" in url:
                        cid = url.split("/c/")[-1].split("/")[0].split("?")[0]
                        if len(cid) >= 30:
                            return cid
        except OSError:
            pass
        time.sleep(10)
    return None


def arm_watch(name, marker):
    w = subprocess.run(
        [sys.executable, os.path.join(BASE, "launch_queue_watch.py"),
         name, name, marker],
        capture_output=True, text=True, timeout=60)
    log(f"queue_watch[{name}] rc={w.returncode} :: "
        f"{(w.stdout or '').strip()[:140]}")


def main():
    if os.path.exists(LOCK):
        try:
            pid = int(open(LOCK).read().strip())
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                if b"r0_redisp_loop" in f.read():
                    log("another instance is live — exiting")
                    return
        except (OSError, ValueError):
            pass
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))

    log(f"=== r0 redisp loop armed — queue: "
        f"{', '.join(n for n, _, _ in QUEUE)}; yields to the login sentinel "
        f"while it lives ===")
    start = time.time()
    fail_noted = set()

    while time.time() - start < MAX_RUNTIME:
        beat()
        if sentinel_running():
            log("login sentinel still running — yielding")
            time.sleep(ROUND_SLEEP)
            continue

        missing = [(n, p, m) for n, p, m in QUEUE if not rs.landed(n)]
        if not missing:
            log("all queue sessions landed — Wave R0 dispatch complete")
            outbox(f"[{TAG}] Wave R0 fully dispatched: post001 COMPLETE "
                   "(harvested), post002 + post003 live with "
                   "supervisor-resurrectable watchers. The resident lead "
                   "harvests their COMPLETION REPORTs and reports back.")
            return

        for name, prompt, marker in missing:
            beat()
            # workspace gate (lesson 131/135)
            count, _ = rs.active_workspace_count()
            if count is not None and count >= rs.SANDBOX_CAP:
                log(f"workspace gate: {count} active >= {rs.SANDBOX_CAP} — "
                    "releasing idle sandboxes before create")
                subprocess.run(
                    [sys.executable, os.path.join(BASE, "dash_sandbox_release.py")],
                    capture_output=True, text=True, timeout=180)
                count, _ = rs.active_workspace_count()
                if count is not None and count >= rs.SANDBOX_CAP:
                    log(f"gate STILL {count} — round deferred")
                    if name not in fail_noted:
                        fail_noted.add(name)
                        outbox(f"[{TAG}] sandbox slots full ({count}/3) — "
                               f"{name} dispatch deferred; the loop retries "
                               "automatically.")
                    break
            else:
                log(f"workspace gate: active={count} (cap {rs.SANDBOX_CAP}) — OK"
                    if count is not None else
                    "workspace gate: API unreadable — proceeding (dispatcher "
                    "concurrency-modal handling is the backstop)")

            log(f"dispatching {name} ({prompt}) — single create, waited")
            rs.pre_clean(name)
            try:
                r = subprocess.run(
                    [sys.executable, os.path.join(BASE, "launch_create.py"),
                     name, os.path.join(BASE, "worker-prompts", prompt)],
                    capture_output=True, text=True, timeout=CREATE_TIMEOUT)
                log(f"create[{name}] rc={r.returncode} :: "
                    f"{(r.stdout or '').strip()[:160]}")
            except subprocess.TimeoutExpired:
                log(f"create[{name}] TIMEOUT after {CREATE_TIMEOUT}s — "
                    "the assault machinery keeps its own bounds; treating "
                    "as a failed round")
            chat_id = registry_chat_id(name, REGISTRY_WAIT)
            if chat_id:
                log(f"registry: {name} -> chat {chat_id} (server-confirmed)")
                arm_watch(name, marker)
                outbox(f"[{TAG}] {name} DISPATCHED from inside the replay "
                       f"(chat {chat_id}) — watching for: {marker}")
                fail_noted.discard(name)
            else:
                log(f"{name}: not landed this round — GLM-5.3 capacity wall; "
                    "next round retries")
                if name not in fail_noted:
                    fail_noted.add(name)
                    outbox(f"[{TAG}] {name} dispatch still blocked by the "
                           "GLM-5.3 capacity wall (model hidden in the menu; "
                           "verified flickering). The loop keeps retrying "
                           "automatically — no operator action needed.")
            time.sleep(30)

        time.sleep(ROUND_SLEEP)

    log("8h window expired — standing down; the lead re-arms on next wake")
    outbox(f"[{TAG}] 8h window expired with sessions still unlanded "
           f"({[n for n, _, _ in QUEUE if not rs.landed(n)]}) — standing "
           "down; the lead re-arms on the next wake.")
    return


if __name__ == "__main__":
    main()
