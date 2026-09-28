#!/usr/bin/env python3
"""s3_login_sentinel.py — dispatch TL2-S3 when the operator's login returns.

The browser's feature surfaces (agents tab, composer) died with the ~08:05
logout; the token injection restores chat pages read-only but NOT dispatch.
This sentinel polls the login state (localStorage token + the agents-tab
marker via a live-tab probe) and fires launch_create.py for flauz-S3-tl2 on
the first healthy window. Read-only otherwise; 60s cadence; 12h window.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP

BASE = "/home/z/replay2/scripts"
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "s3_login_sentinel.log")
PY = "/home/z/.venv/bin/python3"
MARKER = os.path.join(FLAGS, "s3-dispatched.marker")
CADENCE = 60
MAX_WAIT = 12 * 3600


def log(line):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(LOG, "a") as f:
        f.write(f"{stamp} {line}\n")


def login_healthy():
    """True ONLY when the agents-tab FEATURE SURFACE is dispatchable — the
    token-injected state renders chat pages but the Agent tab stays inert
    (production proof 08:35-08:45: three create attempts failed on the
    'New Task' marker under the injected state). Click through and probe."""
    try:
        tab = channel.new_tab("https://chat.z.ai/")
        if tab is None:
            return False
        time.sleep(6)
        c = CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            tok = int(c.eval("(localStorage.getItem('token') || '').length", timeout=8) or 0)
            if tok < 50:
                c.close(); return False
            r = c.eval("""(() => {
              const els = Array.from(document.querySelectorAll('a, button, [role=tab], div'))
                .filter(e => (e.innerText || '').trim() === 'Agent');
              if (!els.length) return 'no-el';
              els[els.length-1].click();
              return 'clicked';
            })()""", timeout=12)
            if not str(r).startswith("clicked"):
                c.close(); return False
            time.sleep(6)
            body = c.eval("document.body.innerText || ''", timeout=15) or ""
            healthy = ("New Task" in body) and ("Sign in" not in body)
            c.close()
            return healthy
        except Exception:
            try:
                c.close()
            except Exception:
                pass
            return False
        finally:
            try:
                import urllib.request
                urllib.request.urlopen(
                    f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
            except Exception:
                pass
    except Exception:
        return False


def main():
    if os.path.exists(MARKER):
        log("S3 already dispatched — sentinel stands down")
        return
    log("=== s3_login_sentinel start (waiting for operator login)")
    started = time.time()
    while time.time() - started < MAX_WAIT:
        if login_healthy():
            log("LOGIN HEALTHY — dispatching S3")
            subprocess.Popen(
                [PY, os.path.join(BASE, "launch_create.py"),
                 "flauz-S3-tl2",
                 os.path.join(BASE, "worker-prompts", "flauz-tl2-s3.md")],
                stdout=open(os.path.join(BASE, "logs", "s3-dispatch.out"), "a"),
                stderr=subprocess.STDOUT, start_new_session=True, cwd=BASE)
            with open(MARKER, "w") as f:
                f.write(f"{int(time.time())}\n")
            # notify the operator via outbox
            try:
                with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
                    f.write(json.dumps({
                        "ts": int(time.time() * 1000), "from": "agent",
                        "text": "[TL2] login detected — S3 (runtime verification) "
                                "dispatched. Watch + harvest armed."}) + "\n")
            except OSError:
                pass
            log("S3 dispatched — sentinel exits")
            return
        time.sleep(CADENCE)
    log("12h window expired — sentinel stands down (re-arm on next session)")


if __name__ == "__main__":
    main()
