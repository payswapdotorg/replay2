#!/usr/bin/env python3
"""h3d_click.py — scroll an element into view (instant), settle, report its
viewport position + elementFromPoint hit test. Then (optionally, with --click)
issue a trusted replayd click at that position.

Usage: h3d_click.py <js-predicate>         # locate + report
       h3d_click.py --click <js-predicate> # locate + trusted click
The js-predicate must be an EXPRESSION returning an Element or null.
"""
import json
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

TEMPLATE = r"""(() => {
  const el = (%s);
  if (!el) return JSON.stringify({found: false});
  el.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = el.getBoundingClientRect();
  const cx = r.x + r.width/2, cy = r.y + r.height/2;
  const at = document.elementFromPoint(cx, cy);
  return JSON.stringify({
    found: true,
    x: Math.round(cx), y: Math.round(cy),
    w: Math.round(r.width), h: Math.round(r.height),
    hit: at ? (at.tagName + '.' + (at.className || '').toString().slice(0, 25)) : 'none',
    selfOrChild: at === el || el.contains(at),
    txt: (el.textContent || '').trim().slice(0, 40).replace(/\n/g, '|')
  });
})()"""


def replay_click(x, y):
    body = json.dumps({"type": "click", "x": x, "y": y}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:3100/event", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()[:200]


def main():
    args = [a for a in sys.argv[1:]]
    do_click = "--click" in args
    pred = [a for a in args if not a.startswith("--")][0]
    js = TEMPLATE % pred
    # pass 1: scroll into view
    tabs = channel.list_tabs()
    h3d = [t for t in tabs if "hyper3d" in (t.get("url") or "")]
    if not h3d:
        print(json.dumps({"error": "no tab"}))
        return
    ws = channel.CDP(h3d[0]["webSocketDebuggerUrl"])
    try:
        r1 = json.loads(ws.eval(js, await_promise=False, timeout=15))
    finally:
        ws.close()
    if not r1.get("found"):
        print(json.dumps({"found": False}))
        return
    time.sleep(0.8)  # settle any layout
    # pass 2: re-measure (position may shift after scroll), fresh connection
    tabs = channel.list_tabs()
    h3d = [t for t in tabs if "hyper3d" in (t.get("url") or "")]
    ws = channel.CDP(h3d[0]["webSocketDebuggerUrl"])
    try:
        r2 = json.loads(ws.eval(js, await_promise=False, timeout=15))
    finally:
        ws.close()
    out = dict(r2)
    if do_click and r2.get("found"):
        out["click"] = replay_click(r2["x"], r2["y"])
    print(json.dumps(out))


if __name__ == "__main__":
    main()
