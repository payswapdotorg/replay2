#!/usr/bin/env python3
"""resident_poll.py — one resident-cycle status report.

Prints:
  1. NEW operator messages since the last poll (watermark in
     flags/inbox_seen_by_agent — lines seen; operator messages get surfaced)
  2. worker session states (from flags/session_registry.jsonl + live DOM):
     chars, streaming marker, completion-report marker present
  3. stack health (console :3000, CDP :9222, replayd :3100, watcher, supervisor)

Run me every ~1-2 minutes; act on what changes.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
WM = os.path.join(FLAGS, "inbox_seen_by_agent")


def http_ok(url, timeout=4):
    try:
        urllib.request.urlopen(url, timeout=timeout).read(64)
        return True
    except Exception:
        return False


def new_operator_messages():
    path = os.path.join(FLAGS, "operator_inbox.jsonl")
    lines = []
    try:
        lines = [l for l in open(path, encoding="utf-8").read().split("\n") if l.strip()]
    except Exception:
        pass
    prev = 0
    try:
        prev = int(open(WM).read().strip() or "0")
    except Exception:
        pass
    out = []
    for l in lines[prev:]:
        try:
            d = json.loads(l)
            if d.get("from") == "operator":
                out.append(str(d.get("text", ""))[:500])
        except Exception:
            pass
    try:
        open(WM, "w").write(str(len(lines)))
    except Exception:
        pass
    return out


def sessions():
    try:
        return [json.loads(l) for l in open(REG).read().split("\n") if l.strip()]
    except Exception:
        return []


def tab_by_id(tid):
    try:
        for t in channel.list_tabs():
            if t.get("id") == tid:
                return t
    except Exception:
        pass
    return None


def session_state(s):
    tab = tab_by_id(s.get("tab_id", ""))
    if not tab:
        return {"state": "TAB-LOST", "chars": 0, "streaming": False, "report": False, "tail": ""}
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=15)
        try:
            body = c.eval("document.body.innerText || ''", timeout=15) or ""
        finally:
            c.close()
        streaming = any(m in body for m in ("Thinking", "Generating", "typing…"))
        report = "COMPLETION REPORT" in body
        tail = [l for l in body.split("\n") if l.strip()][-3:]
        return {"state": "live", "chars": len(body), "streaming": streaming,
                "report": report, "tail": " | ".join(t[-2:] for t in tail)[:300]}
    except Exception as e:
        return {"state": f"ERR:{e!r}", "chars": 0, "streaming": False, "report": False, "tail": ""}


def proc_alive(pattern):
    import subprocess
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return bool(r.stdout.strip())


def main():
    print(f"=== resident poll {time.strftime('%H:%M:%S')} ===")
    msgs = new_operator_messages()
    if msgs:
        for m in msgs:
            print(f">>> NEW OPERATOR MESSAGE: {m}")
    else:
        print("operator inbox: no new messages")
    for s in sessions():
        st = session_state(s)
        flag = ""
        if st["report"] and not st["streaming"]:
            flag = " *** REPORT READY ***"
        elif st["report"]:
            flag = " (report forming…)"
        print(f"worker {s['name']:8} {st['state']:10} chars={st['chars']:7} "
              f"streaming={st['streaming']}{flag}")
        if st["tail"]:
            print(f"    tail: {st['tail'][:240]}")
    health = {
        "console:3000": http_ok("http://127.0.0.1:3000"),
        "cdp:9222": http_ok("http://127.0.0.1:9222/json/version"),
        "replayd:3100": http_ok("http://127.0.0.1:3100/healthz"),
        "watcher": proc_alive("scripts/watcher.py"),
        "supervisor": proc_alive("scripts/supervisor.py"),
    }
    dead = [k for k, v in health.items() if not v]
    print("stack:", "ALL UP" if not dead else f"DEAD: {dead}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
