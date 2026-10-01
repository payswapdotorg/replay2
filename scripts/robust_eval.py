#!/usr/bin/env python3
"""robust_eval.py — run an in-page JS (await_promise) on the FIRST responsive
chat.z.ai tab. Usage: robust_eval.py <file-with-js or - for stdin> [timeout]"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def robust_eval(js, timeout=45, want_all=False):
    results = []
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    # prefer tabs NOT currently navigating: try each with a short probe
    for t in tabs:
        try:
            ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=10)
            try:
                ws.eval("1", await_promise=False, timeout=6)
                r = ws.eval(js, await_promise=True, timeout=timeout)
                results.append((t["id"][:8], r))
                if not want_all:
                    return results[0]
            finally:
                ws.close()
        except Exception:
            continue
    return None if not results else (results[0] if not want_all else results)


if __name__ == "__main__":
    src = sys.stdin.read() if sys.argv[1] == "-" else open(sys.argv[1]).read()
    tmo = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    out = robust_eval(src, timeout=tmo)
    if out is None:
        print("NO-RESPONSIVE-TAB")
        sys.exit(1)
    print(out[0], out[1])
