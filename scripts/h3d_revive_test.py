#!/usr/bin/env python3
"""h3d_revive_test.py — discriminate the after() mystery + unstick the wedge:
(1) create a fresh FAST text-to-3d task — if it completes inline (create
    route's after() carries the pipeline) and its progress carries `at`,
    the freeze-fix build is live and after() executes;
(2) POST /api/task/88ab4d72-fd1e/fallback — the app's own recovery escape
    hatch — and watch the wedged task complete inside the fallback route's
    after() window."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402

WEDGE = "88ab4d72-79ca-4891-a4c7-fd1e9db98526"


def js(ws, expr, t=40):
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

    # ---- (1) fresh fast task: does the create-route after() carry it? ----
    created = js(ws, """(async () => {
      const r = await fetch('/api/task', {
        method: 'POST', credentials: 'include',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({type: 'RodinStandard', prompt: 'a small wooden table with four legs',
          effort: 'low', engine: 'fast', seed: 4242})});
      return JSON.stringify({status: r.status, body: await r.json().catch(() => null)});
    })()""")
    print("[create]", created, flush=True)
    new_uuid = None
    try:
        new_uuid = json.loads(created)["body"]["uuid"]
    except Exception:
        pass
    if new_uuid:
        for i in range(12):
            c = js(ws, """(async () => {
              const r = await fetch('/api/task/card/%s', {credentials: 'include', cache: 'no-store'});
              const j = await r.json(); const s = j.settings || {};
              return JSON.stringify({state: j.user_state, engine: s.engine_used || null,
                has_at: !!(s.progress && typeof s.progress.at === 'number'), gen_time: !!j.generate_time});
            })()""" % new_uuid)
            print(time.strftime("%H:%M:%S"), "[fresh]", c, flush=True)
            d = json.loads(c)
            if d.get("state") in ("DonePreview", "done", "failed"):
                break
            time.sleep(5)

    # ---- (2) fallback-revive the wedged task ----
    fb = js(ws, """(async () => {
      const r = await fetch('/api/task/%s/fallback', {
        method: 'POST', credentials: 'include',
        headers: {'content-type': 'application/json'},
        body: JSON.stringify({reason: 'ops revive of a frozen fallback task (2026-10-19 audit)'})});
      return JSON.stringify({status: r.status, body: await r.json().catch(() => null)});
    })()""" % WEDGE)
    print("[fallback]", fb, flush=True)
    for i in range(14):
        c = js(ws, """(async () => {
          const r = await fetch('/api/task/card/%s', {credentials: 'include', cache: 'no-store'});
          const j = await r.json(); const s = j.settings || {};
          return JSON.stringify({state: j.user_state, engine: s.engine_used || null,
            resume_count: s.resume_count ?? null, gen_time: !!j.generate_time,
            has_at: !!(s.progress && typeof s.progress.at === 'number')});
        })()""" % WEDGE)
        print(time.strftime("%H:%M:%S"), "[wedge]", c, flush=True)
        d = json.loads(c)
        if d.get("state") in ("DonePreview", "done", "failed"):
            break
        time.sleep(6)


if __name__ == "__main__":
    main()
