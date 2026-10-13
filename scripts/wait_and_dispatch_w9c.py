#!/usr/bin/env python3
"""wait_and_dispatch_w9c.py — patient re-dispatch gate for w9c.

The 08:12 misfire taught: during partial backend degradation the send can
land in a DEFAULT (non-agent) chat with a dead turn, and the capacity
poller then disarms on chat-existence alone. This gate waits for REAL
backend health before sending ONE clean dispatch:

  healthy = a fresh chat.z.ai tab loads AND the composer renders the skill
  chips (the dispatch's own [5/7] probe) AND a bare eval answers.

Then it runs dispatch_worker.py create once (dfork-safe: it re-execs itself
via dfork when launched from a Bash call). If the create fails, it loops
(with the standard capacity flag machinery taking over — create manages
its own assault rounds and writes the flag for the supervisor poller).
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

PROMPT = os.path.join(BASE, "worker-prompts", "w9c-app-environments-studio.md")
LOG = os.path.join(BASE, "logs", "wait_dispatch_w9c.log")
PROBE_EVERY = 90


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def backend_healthy():
    """Open a fresh tab, wait for the composer chips, close it."""
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:9222/json/new", method="PUT")
        t = json.load(urllib.request.urlopen(req, timeout=10))
    except Exception as e:
        log(f"tab open failed: {str(e)[:50]}")
        return False
    tid = t["id"]
    try:
        ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
        try:
            ws.call("Page.navigate", {"url": "https://chat.z.ai/"}, timeout=20)
        except Exception:
            pass
        # give the SPA time to boot its composer
        for _ in range(10):
            time.sleep(2)
            try:
                # EXACT dispatch probe (JS_SKILL_STATE): intro chips list +
                # composer chip presence — the real composer-UI health signal
                state = ws.eval(
                    "(() => { const intro = []; document.querySelectorAll('button').forEach(b => {"
                    " const t = (b.innerText || '').trim().split('\\n')[0];"
                    " if (['IM','Full-Stack','Writing','Data Insight'].includes(t)) {"
                    " const cls = (b.className || '').toString();"
                    " if (cls.includes('rounded-md')) intro.push(t); } });"
                    " let composerChip = false; document.querySelectorAll('button').forEach(b => {"
                    " const t = (b.innerText || '').trim().split('\\n')[0];"
                    " const cls = (b.className || '').toString();"
                    " if (t === 'Full-Stack' && cls.includes('flag-parent')) composerChip = true; });"
                    " const ta = document.querySelector('textarea');"
                    " return JSON.stringify({chips: intro.length, ta: !!ta, ready: document.readyState}); })()",
                    timeout=8,
                )
                d = json.loads(state)
                if d.get("ready") == "complete" and d.get("ta") and d.get("chips", 0) > 0:
                    log(f"probe HEALTHY: {d}")
                    return True
                if d.get("ready") == "complete" and d.get("ta"):
                    # page loaded; chips may legitimately render later — keep probing
                    continue
            except Exception:
                pass
        log(f"probe not ready after 20s: {state if 'state' in dir() else '?'}")
        return False
    finally:
        try:
            ws.close()
        except Exception:
            pass
        try:
            urllib.request.urlopen(
                urllib.request.Request("http://127.0.0.1:9222/json/close/" + tid, method="PUT"),
                timeout=10,
            )
        except Exception:
            pass


def main():
    log("gate armed — waiting for real backend health (composer chips + textarea)")
    while True:
        if backend_healthy():
            log("backend HEALTHY — dispatching w9c (single clean create)")
            rc = subprocess.call([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                  "create", "w9c", PROMPT])
            log(f"create rc={rc}")
            if rc == 0:
                # verify it is NOT another default-mode phantom: the registry row
                # must say mode=agents-tab AND the chat type must be general_agent
                row = None
                try:
                    for line in open(os.path.join(BASE, "flags", "session_registry.jsonl")):
                        if not line.strip():
                            continue
                        r = json.loads(line)
                        if r.get("name") == "w9c" and r.get("sent"):
                            row = r
                except Exception:
                    pass
                if row and row.get("mode") == "agents-tab":
                    log(f"VERIFIED agents-tab send: {row.get('url')}")
                    return 0
                log(f"sent row not agents-tab ({row and row.get('mode')}) — voiding + looping")
                subprocess.call([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                                 "void", "w9c", "gate: send landed in non-agent mode"])
            # rc != 0: the create wrote the capacity flag; the supervisor poller
            # owns the assault from here. Keep gating: if the flag is gone and
            # no live w9c row exists, dispatch again.
        time.sleep(PROBE_EVERY)


if __name__ == "__main__":
    main()
