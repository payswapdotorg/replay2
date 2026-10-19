#!/usr/bin/env python3
"""h3d_watch.py — dedicated monitor for the hyper3d-build worker chat.

v2: completion detection via SERVER message tree, not DOM text (the work
order prompt itself contains 'BUILD COMPLETE' — DOM matching false-positives).
Poll cycle:
  1. GET /api/v1/chats/<id> (Bearer) -> message tree
  2. completion = latest assistant message has content len>0 AND contains
     'BUILD COMPLETE'  -> write flags/H3D_BUILD_COMPLETE
  3. turn-open = latest assistant len==0 (still streaming or dead) —
     discriminate via DOM bodyLen movement; static > STALL_AFTER -> flags/H3D_STALLED
  4. DOM tail logged each cycle for operator visibility
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from channel import CDP, find_tab  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "flags", "h3d_watch.log")
CHAT = "2ec65694-072c-418c-bce7-6fdddd3c572f"
POLL = 30
STALL_AFTER = 1500  # 25 min no DOM movement while turn open

def log(obj):
    line = "[" + time.strftime("%H:%M:%S") + "] " + json.dumps(obj, ensure_ascii=False)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def grab_tab():
    return find_tab(CHAT[:8])

def api_tree():
    tab = grab_tab()
    if not tab:
        return None
    cdp = CDP(tab["webSocketDebuggerUrl"])
    try:
        js = """
        (async () => {
          const t = localStorage.getItem('token') || '';
          const r = await fetch('/api/v1/chats/""" + CHAT + """', {credentials:'include', headers: {'Authorization': 'Bearer ' + t}});
          return (await r.text()).slice(0, 500000);
        })()"""
        raw = cdp.eval(js, await_promise=True, timeout=60)
        d = json.loads(raw)
        hist = (d.get("chat") or {}).get("history") or {}
        msgs = list((hist.get("messages") or {}).values())
        out = []
        for m in msgs:
            c = m.get("content")
            if isinstance(c, str):
                out.append({"role": m.get("role"), "ts": m.get("createdAt") or m.get("ts"), "len": len(c), "text": c})
            else:
                out.append({"role": m.get("role"), "ts": m.get("createdAt") or m.get("ts"), "len": 0, "text": ""})
        return out
    except Exception as e:
        return {"error": str(e)[:150]}
    finally:
        cdp.close()

def dom_probe():
    try:
        tab = grab_tab()
        if not tab:
            return {"err": "no-tab"}
        cdp = CDP(tab["webSocketDebuggerUrl"])
        try:
            expr = r"""JSON.stringify({
  bodyLen: document.body.innerText.length,
  stopBtn: !!document.querySelector('button[class*="stop"], [data-testid*="stop"]'),
  tail: document.body.innerText.slice(-250).replace(/[\n\r]+/g, " | ")
})"""
            return json.loads(cdp.eval(expr, timeout=20))
        finally:
            cdp.close()
    except Exception as e:
        return {"err": str(e)[:120]}

def main():
    last_len = None
    last_move = time.time()
    while True:
        tree = api_tree()
        dom = dom_probe()
        now = time.time()
        if isinstance(tree, dict) and "error" in tree:
            log({"event": "api-error", "err": tree["error"], "dom": dom.get("bodyLen")})
            time.sleep(POLL)
            continue
        assistants = [m for m in tree if m["role"] == "assistant"] if tree else []
        latest_asst = assistants[-1] if assistants else None
        rec = {"event": "poll", "msgs": len(tree or []),
               "asstLen": (latest_asst or {}).get("len"),
               "bodyLen": dom.get("bodyLen"), "stopBtn": dom.get("stopBtn")}
        # 1) completion check — SERVER content, not DOM
        if latest_asst and latest_asst.get("len", 0) > 0:
            txt = latest_asst.get("text", "")
            if "BUILD COMPLETE" in txt:
                log({"event": "BUILD-COMPLETE", "asstLen": latest_asst["len"]})
                with open(os.path.join(BASE, "flags", "H3D_BUILD_COMPLETE"), "w") as f:
                    f.write(str(int(now)))
                return
            else:
                rec["turnEnded"] = True
                rec["tailText"] = txt[-250:].replace("\n", " | ")
        # 2) stall discrimination
        bl = dom.get("bodyLen")
        if isinstance(bl, int) and bl != last_len:
            last_len = bl
            last_move = now
        else:
            rec["staticFor"] = int(now - last_move)
            if (latest_asst or {}).get("len", 0) == 0 and rec["staticFor"] >= STALL_AFTER:
                log({"event": "STALLED", "staticFor": rec["staticFor"], "tail": (dom.get("tail") or "")[-200:]})
                with open(os.path.join(BASE, "flags", "H3D_STALLED"), "w") as f:
                    f.write(str(int(now)))
                return
        if "turnEnded" in rec or rec.get("staticFor", 0) >= 300 or "event" not in rec:
            log(rec)
        elif int(now) % 120 < POLL:
            log(rec)
        time.sleep(POLL)

if __name__ == "__main__":
    main()
