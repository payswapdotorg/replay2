#!/usr/bin/env python3
"""arm_on_landing.py <name> <marker> — wait for a dispatch to land, arm queue_watch.

Companion to recover_capacity.py (which re-runs the aggressive create loop
but does not arm a watcher). This daemon polls the session registry for
<name>; when a record with a URL exists AND the chat is live server-side,
it launches queue_watch via the sanctioned launcher and exits. Bounded to
~10h; the worklog carries the manual fallback (launch_queue_watch.py by
hand) if this daemon dies with the sandbox.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import dispatch_worker as dw  # noqa: E402

NAME = sys.argv[1]
MARKER = sys.argv[2] if len(sys.argv) > 2 else "COMPLETION REPORT"
MAX_S = int(os.environ.get("ARM_MAX_S", "36000"))


def chat_live(cid):
    try:
        import urllib.request
        tok = open(os.path.join(BASE, "flags", "chat_token")).read().strip().strip('"')
        rq = urllib.request.Request(f"https://chat.z.ai/api/v1/chats/{cid}",
                                    headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(rq, timeout=15) as r:
            return r.status == 200
    except Exception:
        return None


def log(msg):
    print(f"[arm-on-landing:{NAME}] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def main():
    t0 = time.time()
    log(f"waiting for {NAME} to land (marker: {MARKER[:40]})")
    while time.time() - t0 < MAX_S:
        try:
            recs = [s for s in dw._sessions() if s.get("name") == NAME and s.get("url")]
            if recs:
                rec = recs[-1]
                cid = rec["url"].split("/c/")[-1].split("/")[0].split("?")[0]
                live = chat_live(cid)
                if live:
                    tab = (rec.get("tab_id") or "")[:8]
                    log(f"LANDED: chat {cid[:12]} tab {tab} — arming queue_watch")
                    subprocess.call([sys.executable, os.path.join(BASE, "launch_queue_watch.py"),
                                     NAME, tab, MARKER], cwd=BASE)
                    log("queue_watch armed — exiting")
                    return 0
                log(f"record exists but chat not live yet ({live}) — waiting")
        except Exception as e:
            log(f"poll error: {e!r}")
        time.sleep(60)
    log("timeout — manual fallback: launch_queue_watch.py (see worklog)")
    return 3


if __name__ == "__main__":
    sys.exit(main())
