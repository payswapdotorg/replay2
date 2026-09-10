#!/usr/bin/env python3
"""status_all.py — compact status of all worker tracks + watchers.

Shows: queue-watch tail, per-session page state (busy/queued/idle + last
terminal line), workspace pod status, and heartbeat freshness.
"""
import json
import os
import subprocess
import sys
import time
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))


def log_tail(path, n=4):
    try:
        with open(path) as f:
            lines = f.read().strip().split("\n")
        return lines[-n:]
    except Exception:
        return ["(no log)"]


def session_state(url_frag):
    tabs = channel.list_tabs()
    tab = next((t for t in tabs if url_frag in (t.get("url") or "")), None)
    if not tab:
        return None, "TAB-LOST"
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        # 2026-09-10 lesson: session pages WEDGE mid-turn (render freezes while
        # the worker keeps running server-side). Reload before reading so the
        # text is fresh; the reload never disturbs the server-side turn.
        try:
            ws.call("Page.reload", {}, timeout=20)
            time.sleep(4)
        except Exception:
            pass
        busy = ws.eval("Array.from(document.querySelectorAll('button')).some(b=>/^(Stop|Pause|Halt)$/i.test((b.innerText||'').trim())) ? 'busy' : 'idle'", timeout=15)
        txt = ws.eval("document.body.innerText", timeout=25) or ""
        # last non-empty line that isn't UI chrome
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        tail = ""
        for l in reversed(lines[-40:]):
            if len(l) > 15 and not l.startswith(("Download", "Publish", "Thought", "Show full")):
                tail = l[:110]
                break
        import re as _re
        report = bool(_re.search(
            r"=== WO-\d+ (?:COMPLETION REPORT|完成报告) ==="
            r"[\s\S]{0,600}?(?:base branch|基础分支)\s*\+\s*(?:base SHA|基础\s*SHA)\s*[:：]\s*main\s*@\s*[0-9a-f]{7,40}",
            txt))
        gen = bool(_re.search(r"\b(Stop|Pause|Halt)\b", txt[-1500:]))
        return (busy + ("/GEN" if gen else "")), f"{tail}{' [REPORT!]' if report else ''}"
    finally:
        ws.close()


def main():
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"=== status_all @ {now}")
    # heartbeats
    for f in ("heartbeat", "supervisor_heartbeat", "watcher_heartbeat", "custodian_heartbeat",
              "queue_watch_heartbeat.wo-012", "queue_watch_heartbeat.wo-013"):
        p = os.path.join(BASE, "flags", f)
        try:
            age = int(time.time() - os.path.getmtime(p))
            print(f"  hb {f}: {age}s")
        except Exception:
            print(f"  hb {f}: MISSING")
    # queue watch log
    print("--- queue-watch tail:")
    for l in log_tail(os.path.join(BASE, "logs", "queue-watch.log"), 4):
        print("   ", l[:120])
    # sessions
    for name, frag in (("wo-012(new)", "75bbfb60"),
                       ("wo-013(new)", "670b1050"),
                       ("wo-013(old)", "88cacce2")):
        try:
            busy, tail = session_state(frag)
            print(f"--- {name}: {busy}")
            print("    ", tail)
        except Exception as e:
            print(f"--- {name}: ERROR {e!r}")
    # workspaces
    try:
        out = subprocess.run([sys.executable, os.path.join(BASE, "check_workspaces.py")],
                             capture_output=True, text=True, timeout=90)
        for line in out.stdout.split("\n"):
            if line.startswith("== status") or '"status"' in line:
                print("   ", line.strip()[:130])
    except Exception as e:
        print("    workspaces check failed:", e)


if __name__ == "__main__":
    main()
