#!/usr/bin/env python3
"""post_login_rearm.py — the one-shot post-login recovery burst.

Run when the outage monitor reports LOGIN RECOVERED. Does, in order:
  1. Opens fresh tabs on the live lane chats (r36 b764f1bd, r37 f7f04c45,
     r35b's chat is re-dispatched fresh instead).
  2. Writes the queue_watch spec files with the correct tab prefixes.
  3. Arms queue_watch per lane (the supervisor then owns their immortality).
  4. Launches the r35b fresh full-packet dispatch (assault daemon).
  5. Nudges the stalled lanes (r36 + r37) with the re-entry directive.
Logs to logs/post-login-rearm.log. Idempotent-ish: skips what's already done.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "post-login-rearm.log")
PY = sys.executable

LANES = {
    "r36": {"chat": "b764f1bd-9f36-4d0f-8f47-b39984d32c89",
            "marker": "=== R36 COMPLETION REPORT ==="},
    "r37": {"chat": "f7f04c45-593d-43f8-ba0b-361a71b34319",
            "marker": "=== R37 COMPLETION REPORT ==="},
}

NUDGES = {
    "r36": ("CONTINUE R36 — your turn ended at the 'Re-run web typecheck' step (re-export/page.tsx/"
            "ChannelSurface narrowing fixes just written). RESUME: the typecheck, the remaining tabs "
            "wiring, the bell record, J43, then ALL guards + the bundle relay + the report. Reply "
            "with your first action, then keep working."),
    "r37": ("CONTINUE R37 — your turn ended during the STEP ZERO survey. RESUME: finish the survey "
            "(catalog live-declaration options, watch seams, transport choice), then the six work "
            "surfaces, J44/J45, guards, relay + report. Reply with your first action, then keep working."),
}


def log(msg):
    line = time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def tabs():
    with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=15) as r:
        return json.load(r)


def close_tab(tid):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{tid}", timeout=10).read()
    except Exception:
        pass


def open_tab(url):
    req = urllib.request.Request(
        f"http://127.0.0.1:9222/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    log("post-login re-arm burst starting")
    # 1-3: lanes
    for name, lane in LANES.items():
        chat = lane["chat"]
        # close any stale tab on this chat, open fresh
        for t in tabs():
            if chat[:18] in (t.get("url") or ""):
                close_tab(t["id"])
                log(f"{name}: closed stale tab {t['id'][:8]}")
        time.sleep(1)
        t = open_tab(f"https://chat.z.ai/c/{chat}")
        tid = (t.get("id") or "")[:8]
        log(f"{name}: fresh tab {tid} on chat {chat[:8]}")
        # verify it loaded the chat (not bounced home)
        time.sleep(14)
        for tb in tabs():
            if (tb.get("id") or "").startswith(tid):
                url = tb.get("url") or ""
                if "/c/" not in url:
                    log(f"{name}: TAB BOUNCED HOME ({url[:50]}) — login may not be effective; aborting re-arm")
                    return 1
        # write the spec + arm the watcher
        spec = {"name": name, "tab_prefix": tid, "marker": lane["marker"], "pid": 0}
        json.dump(spec, open(os.path.join(FLAGS, f"queue_watch.spec.{name}"), "w"))
        subprocess.Popen(
            [PY, os.path.join(BASE, "queue_watch.py"), name, tid, lane["marker"]],
            stdout=open(os.path.join(BASE, "logs", f"queue_{name}_rearm.log"), "a"),
            stderr=subprocess.STDOUT, start_new_session=True)
        log(f"{name}: queue_watch armed on {tid}")
        # 5: the nudge
        npath = os.path.join(FLAGS, f"{name}-nudge.txt")
        open(npath, "w").write(NUDGES[name])
        r = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                            "send", name, f"@{npath}"],
                           capture_output=True, text=True, timeout=300)
        tail = (r.stdout or "").strip().splitlines()[-1:] or ["(none)"]
        log(f"{name}: nudge → {tail[0][:120]}")
        time.sleep(5)
    # 4: the r35b fresh dispatch
    log("r35b: launching the fresh full-packet dispatch (assault daemon)")
    subprocess.Popen(
        [PY, os.path.join(BASE, "assault_daemon.py"), "r35b",
         os.path.join(BASE, "worker-prompts", "r35b-journeys.md")],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
    log("post-login re-arm burst complete — the wave is live again")
    return 0


if __name__ == "__main__":
    sys.exit(main())
