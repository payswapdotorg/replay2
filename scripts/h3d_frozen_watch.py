#!/usr/bin/env python3
"""h3d_frozen_watch.py — watch the frozen fallback task 88ab4d72-fd1e:
poll its card every 15s x N, printing state + resume_count, to test whether
the card-poll freeze-recovery revives it on production."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402

UUID = "88ab4d72-79ca-4891-a4c7-fd1e9db98526"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def js(ws, expr, t=30):
    return ws.eval(expr, await_promise=True, timeout=t)


def main():
    tab = next(t for t in list_tabs() if "hyper3d-clone.vercel.app" in (t.get("url") or ""))
    ws = CDP(tab["webSocketDebuggerUrl"], timeout=20)
    try:
        ws.call("Page.reload", timeout=15)
    except Exception:
        pass
    for _ in range(25):
        try:
            if js(ws, "document.readyState", t=8) == "complete":
                break
        except Exception:
            pass
        time.sleep(1)
    time.sleep(2)
    for i in range(N):
        try:
            r = js(ws, """(async () => {
              const c = await fetch('/api/task/card/%s', {credentials: 'include', cache: 'no-store'});
              const j = await c.json();
              const s = j.settings || {};
              return JSON.stringify({user_state: j.user_state, engine_used: s.engine_used || null,
                resume_count: s.resume_count ?? null, progress: s.progress ?? null,
                gen_time: j.generate_time ?? null});
            })()""" % UUID)
            print(time.strftime("%H:%M:%S"), r, flush=True)
        except Exception as e:
            print(time.strftime("%H:%M:%S"), "ERR:", str(e)[:120], flush=True)
        if i < N - 1:
            time.sleep(15)


if __name__ == "__main__":
    main()
