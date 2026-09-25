#!/usr/bin/env python3
"""r30b_vpn_click.py — REAL mouse click on the turbovpn power button.

The 'Tap to Connect' element ignores synthetic .click(); it needs CDP
Input.dispatchMouseEvent at its center (the manual_send pattern)."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS_RECT = """
(() => {
  const all = [...document.querySelectorAll('*')];
  const el = all.find(e => /^tap to connect$/i.test((e.innerText || '').trim())
                           && e.childElementCount <= 2);
  if (!el) return null;
  const walk = el;
  let x = walk;
  for (let i = 0; i < 3 && x.parentElement; i++) x = x.parentElement;
  const r = x.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2,
                         w: r.width, h: r.height});
})()
"""

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({head: t.trim().split('\\n').slice(0, 8),
                         connected: /connected|protecting/i.test(t)});
})()
"""


def main():
    tabs = [t for t in channel.list_tabs()
            if "piplkafkogjfjlofefcobgiccagncean" in (t.get("url") or "")]
    if not tabs:
        print("no popup tab")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
    try:
        rect = c.eval(JS_RECT, timeout=12)
        if not rect or rect == "null":
            print("POWER ELEMENT NOT FOUND")
            return 1
        d = json.loads(rect)
        print(f"power button center: ({d['x']:.0f},{d['y']:.0f}) size {d['w']:.0f}x{d['h']:.0f}")
        for typ in ("mousePressed", "mouseReleased"):
            c.call("Input.dispatchMouseEvent", {
                "type": typ, "x": d["x"], "y": d["y"],
                "button": "left", "clickCount": 1})
        print("mouse click dispatched")
        for i in range(6):
            time.sleep(5)
            try:
                st = c.eval(JS_STATE, timeout=10)
                print(f"[{i * 5 + 5}s]", st[:300])
                sd = json.loads(st)
                if sd.get("connected"):
                    print("VPN CONNECTED!")
                    return 0
            except Exception as e:
                print(f"[{i * 5 + 5}s] eval: {type(e).__name__}")
        return 2
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
