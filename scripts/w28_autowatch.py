#!/usr/bin/env python3
"""w28_autowatch.py — autonomous W-28 watcher: delivery oracle + generation retry.

State machine (per chat):
  LANDED      chat exists, order in tree, ws bound, turn record open (len=0)
  GENERATING  assistant len > 0 or updated_at moving  -> wait for delivery
  STALLED     frozen >= STALL_MIN with len=0          -> re-dispatch via the
              PROVEN dispatch_capture_replay path (agents tab, GLM-5.2 menu,
              full send ladder, capture + verbatim-replay fallback)
  DELIVERED   branch work/W28-neon-ddl-runbook-b on remote -> exit (TL harvests)

Usage: w28_autowatch.py <chat-uuid> [attempt-prefix]
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

BRANCH = "work/W28-neon-ddl-runbook-b"
REPO = "/home/z/TradRL"
TICK = os.path.join(BASE, "flags", "w28_autowatch.tick")
LOG = os.path.join(BASE, "flags", "w28_autowatch.log")
ORDER = os.path.join(BASE, "worker-prompts", "tradrl-w28.md")
STALL_MIN = 90          # minutes frozen (len=0) before re-dispatch
POLL_S = 120


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%SZ", time.gmtime()), msg)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def branch_sha():
    try:
        out = subprocess.run(
            ["git", "ls-remote", REPO, "refs/heads/" + BRANCH],
            capture_output=True, text=True, timeout=30).stdout.strip()
        return out.split()[0] if out else ""
    except Exception:
        return ""


def chat_state(chat_id):
    """(updated_at, n_msgs, asst_len) via the site API with the cached JWT."""
    try:
        tok = open(os.path.join(BASE, "flags", "chat_token")).read().strip().strip('"')
        req = urllib.request.Request(
            "https://chat.z.ai/api/v1/chats/" + chat_id,
            headers={"Authorization": "Bearer " + tok,
                     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        h = ((data.get("chat") or {}).get("history")) or {}
        msgs = h.get("messages") or {}
        asst_len = 0
        n = 0
        for m in msgs.values():
            n += 1
            if m.get("role") == "assistant":
                c = m.get("content")
                asst_len = max(asst_len, len(str(c)) if c else 0)
        return int(data.get("chat", {}).get("updated_at") or 0), n, asst_len
    except Exception as e:
        return -1, -1, -1


def redispatch(prefix):
    """Fire the proven dispatch_capture_replay path, dfork'd; return the new chat id."""
    name = "%s-%d" % (prefix, int(time.time()) % 100000)
    logfile = os.path.join(BASE, "logs", "%s.log" % name)
    r = subprocess.run(
        ["python3", "dfork_launch.py", logfile, "python3", "dispatch_capture_replay.py",
         name, ORDER],
        cwd=BASE, capture_output=True, text=True, timeout=60)
    # wait for the dispatch to land, then read the new chat id from the log
    for _ in range(40):
        time.sleep(5)
        try:
            txt = open(logfile, encoding="utf-8", errors="replace").read()
            m = re.search(r"chat\.z\.ai/c/([0-9a-f-]{36})", txt)
            if m:
                return m.group(1)
        except Exception:
            pass
    return ""


def main():
    chat_id = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else "tradrl-w28"
    landed_at = time.time()
    gen_seen = False
    while True:
        sha = branch_sha()
        if sha:
            log("BRANCH-LANDED %s @ %s — TL harvest can begin" % (BRANCH, sha[:7]))
            with open(TICK, "a") as f:
                f.write("%s DELIVERED %s\n" % (time.strftime("%H:%M:%SZ", time.gmtime()), sha[:7]))
            return 0
        ua, n, alen = chat_state(chat_id)
        status = "DEAD-RECORD" if ua < 0 else ("GENERATING" if alen > 0 else "WAITING")
        if alen > 0:
            gen_seen = True
        with open(TICK, "a") as f:
            f.write("%s chat=%s msgs=%d asst_len=%d upd=%d state=%s branch=%s\n"
                    % (time.strftime("%H:%M:%SZ", time.gmtime()), chat_id[:8], n, alen, ua,
                       status, sha[:7] or "-"))
        frozen_min = (time.time() - landed_at) / 60.0
        if ua < 0:
            log("chat record unreadable (wedge?) — re-dispatching")
        elif not gen_seen and alen == 0 and frozen_min >= STALL_MIN:
            log("STALLED %.0f min (len=0, never generated) — re-dispatching" % frozen_min)
        elif gen_seen and frozen_min >= 2.5 * STALL_MIN:
            log("generation seen but frozen %.0f min — re-dispatching" % frozen_min)
        else:
            time.sleep(POLL_S)
            continue
        new_chat = redispatch(prefix)
        if not new_chat:
            log("re-dispatch failed to land — retrying next cycle")
            time.sleep(POLL_S)
            continue
        log("re-dispatch LANDED at /c/%s — switching watch" % new_chat[:13])
        chat_id = new_chat
        landed_at = time.time()
        gen_seen = False
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
