#!/usr/bin/env python3
"""gap5_login_sentinel.py — recycle #18 login sentinel (2026-10-16).

The recycle wiped the browser login AND the durable token; this sentinel
waits for the operator's login on the fresh replay (deployed from
payswapdotorg/replay2 @ d05c9bb), then arms the GAP-5 delivery chain
(the Flauz TL-B frontier work order — gap-ledger row 5, the workbench
node-lane runtime binding):

  on login (30s poll, 24h window, read-only until then):
  1. token capture (chats_http.get_token — also refreshes login_keeper)
  2. dispatch GAP-5 (dispatch_worker create — the AGENTS tab, GLM-5.3,
     Full-Stack doctrine; the built-in capacity fight, never wait)
  3. arm queue_watch[dh-gap5-node-lane] on the created session's chat
     prefix (marker "=== GAP-5 COMPLETION REPORT ===")
  4. outbox notice

Launch detached: dfork_launch.py logs/gap5_sentinel.log <py> gap5_login_sentinel.py
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
MARKER = "=== GAP-5 COMPLETION REPORT ==="
PROMPT = os.path.join(BASE, "worker-prompts", "dh-gap5-node-lane.md")
NAME = "dh-gap5-node-lane"
WINDOW = 24 * 3600


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
    log("LOGIN DETECTED — arming the GAP-5 delivery chain")
    # 1. token capture (login_keeper's cycle snapshots durably too)
    try:
        sys.path.insert(0, BASE)
        import chats_http
        tok = chats_http.get_token()
        log("token captured (%d chars)" % len(tok))
    except Exception as e:
        log("token capture FAILED: %r — dispatch proceeds via CDP" % (e,))
    # 2. dispatch GAP-5 (create fights capacity internally; never waits)
    rc = None
    try:
        r = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                            "create", NAME, PROMPT],
                           capture_output=True, text=True, timeout=1800, cwd=BASE)
        rc = r.returncode
        tail = (r.stdout or "").strip().splitlines()
        log("dispatch create rc=%s: %s" % (rc, tail[-3:] if tail else "no output"))
        if rc != 0:
            log("dispatch stderr tail: %s" % ((r.stderr or "").strip().splitlines()[-3:],))
    except Exception as e:
        log("dispatch create error: %r" % (e,))
    # 3. queue_watch on the created session
    try:
        prefix = registry_prefix_for(NAME)
        r = subprocess.run(
            [PY, os.path.join(BASE, "launch_queue_watch.py"),
             NAME, prefix, MARKER],
            capture_output=True, text=True, timeout=60, cwd=BASE)
        log("queue_watch: %s" % ((r.stdout or "").strip().splitlines()[-1:],))
    except Exception as e:
        log("queue_watch arm error: %r" % (e,))
    # 4. operator notice
    if rc == 0:
        outbox("[lead] LOGIN LANDED — GAP-5 dispatched (recycle #18): the Flauz "
               "gap-ledger row-5 work order (the workbench node-lane runtime "
               "binding — the REAL flauzHarnessPort.ts imported + exercised "
               "against the REAL kits in the node lane, the .js-specifier "
               "resolution solved lawfully, + the row-5 closure per the "
               "closed-row pattern) is generating in the AGENTS tab on "
               "GLM-5.3/Full-Stack, base 7478237a, branch "
               "flauz-tlb/dh-gap5-node-lane. queue_watch owns the resident "
               "monitor (marker: GAP-5 COMPLETION REPORT). On report: harvest "
               "-> station gates -> review -> PR -> merge. GAP-6 WO composes "
               "next. — Tech Lead")
    else:
        outbox("[lead] LOGIN LANDED — GAP-5 dispatch chain armed (recycle #18); "
               "the create is fighting the capacity ladder (the never-wait "
               "doctrine; queue_watch re-dispatches automatically). The Lead "
               "monitors. — Tech Lead")
    log("chain armed — sentinel retiring")


def main():
    log("GAP-5 login sentinel armed (recycle #18, 24h window) — prompt staged: %s" % os.path.exists(PROMPT))
    start = time.time()
    while time.time() - start < WINDOW:
        if logged_in():
            arm()
            return 0
        time.sleep(30)
    log("24h window expired without login — retiring")
    return 1


if __name__ == "__main__":
    sys.exit(main())
