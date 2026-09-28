#!/usr/bin/env python3
"""r38_lanes_probe.py — one-off: reopen tabs for the r38a/r38b server-side
sessions (the 20:31 stall_recovery closes left the watchers tab-blind) and
read the ground truth: completion markers, command counter, todo, stop.
Does NOT send anything. Read-only diagnostic (the A3995F57 pattern).
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

LANES = [
    ("r38a", "3cc258fa-d26e-48c8-a0f5-ad7b6b837082", "R38A COMPLETION REPORT"),
    ("r38b", "271c6d81-244d-4a70-abbe-933f150c58a8", "R38B COMPLETION REPORT"),
]

JS = r"""(() => {
  const b = document.body.innerText || '';
  const ran = (b.match(/Ran (\d+) commands?/) || ['', '0'])[1];
  const todo = (b.match(/Todo Progress[^0-9]*(\d+)\/(\d+)/) || ['', '0', '0']);
  const stop = document.querySelector('[aria-label=Stop]') ? '1' : '0';
  return JSON.stringify({chars: b.length, ran, todo: todo[1] + '/' + todo[2], stop,
                         url: location.href});
})()"""

for name, cid, marker in LANES:
    url = f"https://chat.z.ai/c/{cid}"
    tab = channel.new_tab()
    if not tab:
        print(f"[{name}] could not open tab")
        continue
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        c.call("Page.navigate", {"url": url}, timeout=30)
        time.sleep(12)
        body = ""
        try:
            body = c.eval("document.body.innerText || ''", timeout=20) or ""
        except Exception as e:
            print(f"[{name}] body read fail: {e}")
        info = {}
        try:
            info = json.loads(c.eval(JS, timeout=20) or "{}")
        except Exception as e:
            info = {"err": str(e)}
        hits = body.count(marker) + body.count(marker.replace("COMPLETION REPORT", "完成报告"))
        # last 400 chars — the live tail (report tail / error text / streaming edge)
        tail = body[-400:].replace("\n", "\\n")
        print(f"[{name}] tab={tab['id'][:8]} hits={hits} info={info}")
        print(f"[{name}] TAIL: {tail}")
    finally:
        c.close()
    time.sleep(2)
