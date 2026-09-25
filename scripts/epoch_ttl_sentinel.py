#!/usr/bin/env python3
"""epoch_ttl_sentinel.py — lesson-134 pre-emptive TTL nudges for wave-6 Epoch workers.

For each worker: at T_NUDGE (2h05m) after its turn-start/last-nudge anchor,
if the completion report has NOT rendered, send a continuation nudge via
manual_send.py (the proven in-chat path). Each nudge re-arms the anchor.
Stops nudging a chat after its report renders or after MAX_NUDGES.

Anchors are initialized from the dispatch/resume times recorded in
flags/epoch_ttl_anchors.json (created by the Tech Lead). Nudge files are
per-WO templates under flags/.

Usage: nohup python3 epoch_ttl_sentinel.py >> logs/epoch_ttl_sentinel.log 2>&1 &
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import websocket

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = lambda *a: print(*a, flush=True)

T_NUDGE_S = 2 * 3600 + 5 * 60     # T+2h05m
POLL_S = 5 * 60                   # probe cadence
MAX_NUDGES = 4

WORKERS = [
    ("W012", "931B438C", "e5b4e2d2"),
    ("W020", "40A3E89", "31e04e5e"),
    ("W028", "A9D0741A", "6d452b00"),
]
REPORT_RE = re.compile(r"(Final head:\s+[0-9a-f]{40}|PR:\s+#\d+|CI:\s+(success|failure))")

NUDGE_TMPL = """Continue your {wo} work order NOW, exactly per the Worker Task instructions earlier in this chat. You are mid-turn — do NOT restart from scratch; keep your current progress and continue: finish any remaining implementation, run the FULL verification battery (section 6), push the branch, open the PR via the GitHub API, then post the completion report in EXACTLY the section-8 format ending with the literal line EPOCH-COMPLETION-REPORT {wo} END. Proceed autonomously."""


def tab_body(prefix):
    try:
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=10))
        tab = [t for t in tabs if t.get("id", "").startswith(prefix)]
        if not tab:
            return None
        ws = websocket.create_connection(tab[0]["webSocketDebuggerUrl"], timeout=20)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": "document.body.innerText", "returnByValue": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                ws.close()
                return m.get("result", {}).get("result", {}).get("value")
    except Exception:
        return None


def main():
    anchors_path = os.path.join(FLAGS, "epoch_ttl_anchors.json")
    anchors = json.load(open(anchors_path))          # {wo: {anchor: epoch, nudges: n, done: bool}}
    for wo, _, _ in WORKERS:
        if wo not in anchors:
            anchors[wo] = {"anchor": time.time(), "nudges": 0, "done": False}
    LOG(f"sentinel up; anchors: " + json.dumps({k: (int(v['anchor']), v['nudges'], v['done']) for k, v in anchors.items()}))
    while True:
        now = time.time()
        changed = False
        for wo, tabp, cid in WORKERS:
            st = anchors[wo]
            if st["done"]:
                continue
            body = tab_body(tabp)
            if body and REPORT_RE.search(body[-3000:]):
                st["done"] = True
                changed = True
                LOG(f"[{wo}] completion report rendered — TTL watch closed")
                continue
            if st["nudges"] >= MAX_NUDGES:
                continue
            if now - st["anchor"] < T_NUDGE_S:
                continue
            # report not rendered and the TTL wall (~2h22m) approaches: nudge
            nudge_file = os.path.join(FLAGS, f"ttl_nudge_{wo}.md")
            with open(nudge_file, "w") as f:
                f.write(NUDGE_TMPL.format(wo=wo))
            r = subprocess.run([sys.executable, os.path.join(BASE, "manual_send.py"), cid, nudge_file],
                               capture_output=True, text=True, timeout=180)
            ok = "SENT-VERIFIED" in (r.stdout + r.stderr)
            LOG(f"[{wo}] TTL nudge #{st['nudges'] + 1}: {'SENT-VERIFIED' if ok else 'FAILED'}"
                f"{' :: ' + (r.stdout + r.stderr).strip().splitlines()[-1][:120] if not ok else ''}")
            if ok:
                st["nudges"] += 1
                st["anchor"] = now
                changed = True
        with open(anchors_path, "w") as f:
            json.dump(anchors, f, indent=1)
        if all(anchors[wo]["done"] for wo, _, _ in WORKERS):
            LOG("all workers reported — sentinel exiting")
            return
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
