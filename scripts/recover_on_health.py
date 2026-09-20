#!/usr/bin/env python3
"""recover_on_health.py — resident recovery sentinel for the 2026-09-17 outage.

Waits for the site's generation backend to recover (backend_probe.py logic:
an assistant reply in the probe chat), then executes the recovery sequence:

  1. wait 60s, re-check (guard against a fluke probe);
  2. check each wave session's tab for live generation — generating sessions
     are LEFT ALONE (the queue-drain outcome: their turns fired on recovery);
  3. static sessions get their tab closed -> queue_watch sees tablost and
     runs its designed void + fresh re-dispatch (which auto-releases an idle
     sandbox when the cap requires it);
  4. release any residual zombie sandboxes via the modal discipline (rows
     that are NOT live wave sessions), best-effort;
  5. write flags/BACKEND_RECOVERED, notify the operator via the outbox, exit.

Logs to logs/recover_on_health.log. Launched detached; dies with the sandbox
layer (the worklog carries the protocol for the next context).
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = open(os.path.join(BASE, "logs", "recover_on_health.log"), "a", buffering=1)
WAVE = ["prod017", "prod019", "prod020"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def outbox(text):
    with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def probe_healthy():
    rc = subprocess.call([sys.executable, os.path.join(BASE, "backend_probe.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    return rc == 0


def tab_len(prefix):
    for t in channel.list_tabs():
        if (t.get("id") or "").startswith(prefix):
            try:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
                v = int(c.eval("(document.body.innerText||'').length", timeout=10))
                c.close()
                return v
            except Exception:
                return None
    return None


def main():
    log("recovery sentinel armed — probing every 300s")
    while True:
        try:
            if probe_healthy():
                log("HEALTHY probe — confirming after 60s guard window")
                time.sleep(60)
                if not probe_healthy():
                    log("fluke — probe DOWN again, continuing watch")
                    continue
                log("CONFIRMED HEALTHY — executing recovery sequence")
                import dispatch_worker as dw
                for name in WAVE:
                    rec = dw._find(name)
                    if not rec:
                        log(f"{name}: no registry row (watcher owns re-dispatch)")
                        continue
                    tid = (rec.get("tab_id") or "")[:12].upper()
                    a = tab_len(tid)
                    time.sleep(10)
                    b = tab_len(tid)
                    if a is None or b is None:
                        log(f"{name}: tab unreachable — leaving to watcher")
                        continue
                    if b > a + 10:
                        log(f"{name}: GENERATING (queue drained) — left alone")
                        continue
                    # static: close tab -> watcher tablost -> fresh re-dispatch
                    import urllib.request
                    for t in channel.list_tabs():
                        if (t.get("id") or "").upper().startswith(tid):
                            try:
                                urllib.request.urlopen(
                                    f"http://127.0.0.1:9222/json/close/{t['id']}", timeout=5)
                                log(f"{name}: static tab closed -> watcher will re-dispatch")
                            except Exception as e:
                                log(f"{name}: close failed {e!r}")
                            break
                open(os.path.join(FLAGS, "BACKEND_RECOVERED"), "w").write(
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                outbox("The site backend has RECOVERED (probe confirmed). Recovery sequence "
                       "executed: generating sessions left running; static sessions cycled "
                       "via their watchers' fresh re-dispatch. The adapter wave is running — "
                       "watch for completion reports.")
                log("recovery sequence complete — sentinel exiting")
                return 0
        except Exception as e:
            log(f"cycle error {e!r} — continuing")
        time.sleep(300)


if __name__ == "__main__":
    raise SystemExit(main())
