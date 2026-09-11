#!/usr/bin/env python3
"""patient_check.py <name> — poll a (possibly busy) worker tab until it answers.

Busy streaming tabs time out on CDP evals; this retries for up to ~3 minutes
and reports chars/streaming/report markers when the renderer pauses.
"""
import sys, os, time, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import dispatch_worker as _dw


def main():
    name = sys.argv[1]
    s = _dw._find(name)
    if not s:
        print(f"session {name} not found in registry")
        return 1
    tab = None
    for t in channel.list_tabs():
        if t.get("id") == s.get("tab_id"):
            tab = t
            break
    if not tab and s.get("url"):
        for t in channel.list_tabs():
            if s["url"].rstrip("/") in (t.get("url") or ""):
                tab = t
                break
    if not tab:
        print(f"session {name}: tab not found (tab_id={s.get('tab_id','?')[:8]})")
        return 1

    deadline = time.time() + 170
    last_err = ""
    while time.time() < deadline:
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            try:
                body = c.eval("document.body.innerText || ''", timeout=20) or ""
            finally:
                c.close()
            streaming = any(m in body for m in ("Thinking", "Generating", "typing…", "Running"))
            report = "COMPLETION REPORT" in body or "rtn-plan-rulings" in body
            tail = [l for l in body.split("\n") if l.strip()][-4:]
            print(f"{name}: live chars={len(body)} streaming={streaming} report={report}")
            print("tail:", " | ".join(t[:80] for t in tail))
            return 0
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:60]}"
            time.sleep(12)
    print(f"{name}: still busy after retries ({last_err}) — likely actively streaming")
    return 2


if __name__ == "__main__":
    sys.exit(main())
