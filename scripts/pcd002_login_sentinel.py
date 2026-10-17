#!/usr/bin/env python3
"""pcd002_login_sentinel.py — recycle #22 login sentinel (2026-10-17).

The recycle wiped the durable login token (download/zai_session_token.txt)
AND the browser profile's session; this sentinel waits for the operator's
login on the fresh replay, then arms the PCD-002 delivery chain (the
frontier work order of the zeck-competitiveness-p4 program — the operator's
2026-10-14 directive: this station works ONLY on payswapdotorg/Zeck):

  on login (30s poll, 48h window, read-only until then):
  1. capture the chat token (chats_http.get_token -> flags/chat_token)
  2. run the phantom backlog cleanup (safe: only confirmed-0-message
     "New Chat" records <24h old)
  3. dispatch PCD-002 (dispatch_worker create — the AGENTS tab, GLM-5.3,
     Full-Stack doctrine; the built-in capacity fight, never wait)
  4. arm queue_watch[pcd-002] on the created session's chat prefix
     (marker "=== PCD-002 COMPLETION REPORT ===")
  5. outbox notice

Launch detached: dfork_launch.py logs/pcd002_sentinel.log <py> pcd002_login_sentinel.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
STATUS_URL = "http://localhost:3000/api/status"
MARKER = "=== PCD-002 COMPLETION REPORT ==="
PROMPT = os.path.join(BASE, "worker-prompts", "pcd-002-rendered.md")
WINDOW = 48 * 3600


def log(msg):
    line = time.strftime("[%m-%d %H:%M:%S] ") + str(msg)
    print(line, flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000),
                                "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def logged_in():
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=15) as r:
            d = json.loads(r.read().decode())
        return str(d.get("browser_login") or "").startswith("logged-in")
    except Exception:
        return False


def registry_prefix_for(name):
    """The chat URL prefix (first 8 of the chat id) for a created session."""
    try:
        with open(REGISTRY, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        for row in reversed(rows):
            if row.get("name") == name and row.get("url") and "/c/" in str(row.get("url")):
                cid = str(row["url"]).split("/c/")[-1].split("#")[0].split("?")[0]
                return cid[:8]
    except Exception:
        pass
    return "00000000"


def arm():
    log("LOGIN DETECTED — arming the PCD-002 delivery chain")
    # 1. token (also refreshes the durable snapshot via login_keeper's cycle)
    try:
        sys.path.insert(0, BASE)
        import chats_http
        tok = chats_http.get_token()
        log(f"token captured ({len(tok)} chars)")
    except Exception as e:
        log(f"token capture FAILED: {e!r} — dispatch proceeds via CDP")
    # 2. phantom backlog cleanup (safe: only 0-message New-Chat records <24h)
    try:
        cleanup = os.path.join(BASE, "ppr025_phantom_cleanup.py")
        if os.path.exists(cleanup):
            r = subprocess.run([PY, cleanup], capture_output=True, text=True,
                               timeout=240, cwd=BASE)
            tail = (r.stdout or "").strip().splitlines()
            log(f"phantom cleanup: {tail[-1] if tail else 'no output'}")
        else:
            log("phantom cleanup script absent — skipping (fresh account state)")
    except Exception as e:
        log(f"phantom cleanup error: {e!r}")
    # 3. dispatch PCD-002 (create fights capacity internally; never waits)
    rc = None
    try:
        r = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                            "create", "pcd-002", PROMPT],
                           capture_output=True, text=True, timeout=1800, cwd=BASE)
        rc = r.returncode
        tail = (r.stdout or "").strip().splitlines()
        log(f"dispatch create rc={rc}: {tail[-3:] if tail else 'no output'}")
    except Exception as e:
        log(f"dispatch create error: {e!r}")
    # 4. queue_watch on the created session (or a re-arm placeholder prefix —
    #    queue_watch's tablost re-dispatch owns the hunt from there)
    try:
        prefix = registry_prefix_for("pcd-002")
        r = subprocess.run(
            [PY, os.path.join(BASE, "launch_queue_watch.py"),
             "pcd-002", prefix, MARKER],
            capture_output=True, text=True, timeout=60, cwd=BASE)
        log(f"queue_watch: {(r.stdout or '').strip().splitlines()[-1]}")
    except Exception as e:
        log(f"queue_watch arm error: {e!r}")
    # 5. operator notice
    if rc == 0:
        outbox("[lead] LOGIN LANDED — PCD-002 dispatched (recycle #22): the "
               "P3 program's frontier work order (the scorer seam — pluggable adapter + "
               "declarative configuration, default-off/absence-equivalent/ordering-only) is generating in the AGENTS tab on "
               "GLM-5.3/Full-Stack, base c57db171, branch "
               "work/PCD-002-scorer-seam. queue_watch[pcd-002] owns "
               "the resident monitor (marker: PCD-002 COMPLETION REPORT). On "
               "report: harvest -> review -> Lead battery -> PR -> records -> "
               "PCD-003 dispatch. — Tech Lead")
    else:
        outbox("[lead] LOGIN LANDED — PCD-002 dispatch chain armed (recycle "
               "#16); the create is fighting the capacity ladder (queue_watch "
               "re-dispatches automatically). The Lead monitors. — Tech Lead")
    log("chain armed — sentinel retiring")


def main():
    log("pcd-002 login sentinel armed (recycle #22, 48h window)")
    start = time.time()
    while time.time() - start < WINDOW:
        if logged_in():
            arm()
            return 0
        time.sleep(30)
    log("48h window expired without login — retiring")
    return 1


if __name__ == "__main__":
    sys.exit(main())
