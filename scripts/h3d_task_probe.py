#!/usr/bin/env python3
"""h3d_task_probe.py — Task 20 audit: pull the demo account's task list +
the two contested task cards (6d7add2e, 88ab4d72) from PRODUCTION through
the CDP Chrome session. Ground truth for the 02:45Z success-marker audit:
who created which task, when, and what each became."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs, new_tab  # noqa: E402

PROD = "https://hyper3d-clone.vercel.app"
OUT = "/home/z/my-project/research/out/e2e20-task-probe.json"

T1 = "6d7add2e-7e35-47fe-af62-88b953f0de9a"  # the "success" task
T2 = "88ab4d72-79ca-4891-a4c7-fd1e9db98526"  # the CDP Chrome's actual fallback task


def js(ws, expr, t=30):
    return ws.eval(expr, await_promise=True, timeout=t)


def main():
    tab = None
    for t in list_tabs():
        if "hyper3d-clone.vercel.app" in (t.get("url") or ""):
            tab = t
            break
    if tab is None:
        tab = new_tab(PROD)
    ws = CDP(tab["webSocketDebuggerUrl"], timeout=20)
    # revive a possibly-discarded background renderer
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

    data = js(ws, """(async () => {
      const out = {};
      const r = await fetch('/api/task/list?filter=mine', {credentials: 'include', cache: 'no-store'});
      out.list_status = r.status;
      const arr = await r.json().catch(() => null);
      out.list = Array.isArray(arr) ? arr.slice(0, 16).map(t => ({
        uuid: t.task_uuid, time: t.time, user_state: t.user_state,
        engine_used: t.engine_used || null, seed: t.seed ?? null,
        confirmed: t.confirmed ?? null
      })) : arr;
      for (const [k, u] of [['t1', '%s'], ['t2', '%s']]) {
        const c = await fetch('/api/task/card/' + u, {credentials: 'include', cache: 'no-store'});
        const j = await c.json().catch(() => null);
        out[k] = j ? {
          uuid: j.uuid || j.task_uuid, user_state: j.user_state,
          created: j.created_at || j.time || j.createdAt || null,
          engine_used: (j.settings || {}).engine_used || j.engine_used || null,
          fallback_reason: (j.settings || {}).fallback_reason || j.fallback_reason || null,
          confirmed: (j.settings || {}).confirmed, seed: (j.settings || {}).seed,
          prompt: ((j.settings || {}).prompt || '').slice(0, 80),
          mesh_bytes: (j.settings || {}).mesh_bytes ?? null,
          keys: Object.keys(j).slice(0, 24)
        } : {status: c.status};
      }
      return JSON.stringify(out);
    })()""" % (T1, T2), t=45)

    parsed = json.loads(data) if isinstance(data, str) and data.strip().startswith("{") else {"raw": str(data)[:800]}
    with open(OUT, "w") as f:
        json.dump(parsed, f, indent=2, default=str)
    print(json.dumps(parsed, indent=2, default=str)[:4000])


if __name__ == "__main__":
    main()
