#!/usr/bin/env python3
"""Check whether a worker turn body is growing (streaming) over a window."""
import sys
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402


def body_len(cid):
    tab = None
    for t in channel.list_tabs():
        if cid in (t.get("url") or ""):
            tab = t
            break
    if not tab:
        return None
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        n = c.eval("document.body.innerText.length", timeout=20)
        c.close()
        return n
    except Exception as e:
        return "ERR:" + str(e)[:40]


def main():
    cid = sys.argv[1]
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    a = body_len(cid)
    time.sleep(wait)
    b = body_len(cid)
    print("len before=%s after=%s delta=%s -> %s"
          % (a, b,
             (b - a) if (isinstance(a, int) and isinstance(b, int)) else "?",
             "STREAMING" if (isinstance(a, int) and isinstance(b, int) and b > a)
             else ("STATIC/ERR" )))


if __name__ == "__main__":
    main()
