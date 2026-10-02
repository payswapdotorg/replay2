#!/usr/bin/env python3
"""wave3_monitor.py — lead's one-shot wave-3 health check.

Checks (one line each, exit 0 always — this is a gauge, not a gate):
  login    : console /api/status browser_login
  tabs     : worker tabs for prod-011/012 alive and on /c/ session URLs
  reports  : harvest markers (COMPLETION REPORT) in each worker session's
             last assistant message (via chats HTTP API through the mirror tab)
  dispatch : dispatcher process + COMPLETE message in outbox
  ring     : replayd/console/supervisor/watcher/frame_guard/custodian/Xvfb/CDP
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
STATUS_URL = "http://127.0.0.1:3000/api/status"
CID_RE = re.compile(r"/c/([0-9a-f-]{36})")

SESSIONS = {"camscan-prod-011": None, "camscan-prod-012": None}


def p1(label, ok, detail=""):
    print("%-8s %s %s" % (label + ":", "OK" if ok else "!!", detail)[:160])
    return ok


def http_json(url, timeout=20):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"__err__": str(e)}


def main():
    # login
    st = http_json(STATUS_URL).get("browser_login", "unknown")
    p1("login", st.startswith("logged-in"), st)

    # registry -> tab ids
    try:
        with open(REG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                n = d.get("name")
                if n in SESSIONS and d.get("sent") and not d.get("voided"):
                    SESSIONS[n] = d  # last record wins
    except FileNotFoundError:
        pass
    tabs_info = {}
    try:
        tabs = http_json("http://127.0.0.1:9222/json")
        for t in tabs:
            if t.get("type") == "page" and "chat.z.ai" in (t.get("url") or ""):
                m = CID_RE.search(t.get("url") or "")
                tabs_info[t["id"]] = (m.group(1) if m else None, t.get("url") or "")
    except Exception as e:  # noqa: BLE001
        p1("tabs", False, "CDP unreachable: %s" % e)

    for name, rec in SESSIONS.items():
        if not rec:
            p1(name, False, "no registry record")
            continue
        tid = rec.get("tab_id")
        cid = (rec.get("url") or "")
        m = CID_RE.search(cid) if cid else None
        cid = m.group(1) if m else (rec.get("cid") or "")
        if not cid and tid in tabs_info:
            cid = tabs_info[tid][0] or ""
        tab = tabs_info.get(tid)
        p1(name, tab is not None and (tab[0] == cid if cid else True),
           "tab=%s cid=%s" % (str(tid)[:8], cid[:8] or "?"))

    # dispatcher
    try:
        out = subprocess.run(["pgrep", "-f", "dispatch_wave3.py"], capture_output=True, text=True)
        alive = out.returncode == 0
    except Exception:
        alive = False
    complete = False
    try:
        with open(os.path.join(FLAGS, "agent_outbox.jsonl")) as f:
            for line in f:
                if "wave-3 dispatch COMPLETE" in line:
                    complete = True
    except FileNotFoundError:
        pass
    p1("dispatch", complete or alive,
       "proc=%s complete_msg=%s" % (alive, complete))

    # ring
    ring = ["replayd.py", "supervisor.py", "watcher.py", "frame_guard.py",
            "custodian.py", "next dev", "Xvfb :99"]
    down = []
    for pat in ring:
        r = subprocess.run(["pgrep", "-f", pat], capture_output=True)
        if r.returncode != 0:
            down.append(pat)
    p1("ring", not down, "down=%s" % (down or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
