#!/usr/bin/env python3
"""drain_dispatcher — fires the F332P dispatch the moment the platform grants.

Rationale (TL, 2026-10-12 20:10Z): the chat.z.ai agent platform entered a
capacity crunch at ~19:06Z; every dispatch since either never spawned or
wedged its record http-500. The w13b5 (F331B) send is VERIFIED and left for
patience (the platform can unwedge the record when the window drains). This
loop detects the drain — the w13b5 record readable (or resolved 404) AND
a workspace provisioning (or a second sign of life) — and immediately
dispatches the staged F332P worker (the wave's centerpiece: D9 schedules +
the counting gate). One-shot; writes its state to flags/drain_dispatcher.

Drain signals (any ONE fires the dispatch):
  - the w13b5 record turns readable (http-200) — the platform unwedged it
  - a workspace for w13b5 provisions (task spawned server-side)
  - the global workspace total goes >= 1 with an active chat_title

After firing (or on fatal dispatch failure), the loop exits. The TL handles
F331B re-dispatch manually after observing the drain.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/my-project/replay2/scripts")
import chats_http as ch

CID = "7adb5f6f-d1b9-40f2-896c-924cba27d416"
LOG = "/tmp/drain_dispatcher.log"
FLAGS = "/home/z/my-project/replay2/scripts/flags"
PROMPT = "/home/z/my-project/replay2/scripts/worker-prompts/w13f332.md"
TOK = ch.get_token().strip('"')


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def get(path):
    req = urllib.request.Request(
        f"https://chat.z.ai{path}",
        headers={"Authorization": f"Bearer {TOK}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def drain_signal():
    """Return (signal_description or None)."""
    # 1. record readable?
    try:
        data = get(f"/api/v1/chats/{CID}")
        rec = data.get("data", data) if isinstance(data, dict) else {}
        inner = rec.get("chat", {}) or {}
        msgs = inner.get("history", {}).get("messages", {})
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        return f"record readable msgs={len(msgs)}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass  # resolved-destroyed: not by itself a grant signal
        # 500 = still wedged: fall through to workspace check
    except Exception:
        pass
    # 2. workspace provisioned for w13b5?
    try:
        wsd = get("/api/v1/web-dev/workspaces/user-fc")
        for w in wsd.get("workspaces", []):
            if CID in str(w.get("chat_id", "")):
                return "w13b5 workspace provisioned"
        total = wsd.get("total", 0)
        if total >= 1:
            for w in wsd.get("workspaces", []):
                if w.get("chat_title"):
                    return f"workspace total={total} with live title"
    except Exception:
        pass
    return None


def fire():
    log("DRAIN DETECTED — dispatching F332 (w13f332)")
    with open(os.path.join(FLAGS, "drain_dispatcher.fired"), "w") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    r = subprocess.run(
        [sys.executable, "/home/z/my-project/replay2/scripts/dispatch_worker.py",
         "create", "w13f332", PROMPT],
        cwd="/home/z/my-project/replay2",
        capture_output=True, text=True, timeout=600)
    tail = (r.stdout or "").strip().split("\n")[-1:]
    log(f"dispatch exit={r.returncode} tail={tail}")
    return r.returncode


def main():
    log("drain dispatcher start")
    while True:
        sig = drain_signal()
        if sig:
            log(f"signal: {sig}")
            rc = fire()
            log(f"done rc={rc}")
            return rc
        time.sleep(150)


if __name__ == "__main__":
    raise SystemExit(main())
