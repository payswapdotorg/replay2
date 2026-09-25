#!/usr/bin/env python3
"""r30b_vpn_click2.py — click the EXACT 'Tap to Connect' element (not its
page-container ancestors)."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS_RECT = """
(() => {
  const all = [...document.querySelectorAll('*')];
  // the DEEPEST element whose trimmed text is exactly 'Tap to Connect'
  let el = null;
  for (const e of all) {
    if (/^tap to connect$/i.test((e.innerText || '').trim()) &&
        e.children.length <= 3) {
      el = e;  // keep going — deeper matches win
    }
  }
  if (!el) return null;
  // walk up at most ONE level to the nearest clickable shell
  let t = el;
  const style = getComputedStyle(t);
  if (style.cursor !== 'pointer' && t.parentElement) {
    const ps = getComputedStyle(t.parentElement);
    if (ps.cursor === 'pointer') t = t.parentElement;
  }
  const r = t.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2,
                         w: r.width, h: r.height,
                         cursor: getComputedStyle(t).cursor,
                         tag: t.tagName, cls: String(t.className).slice(0, 60)});
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
            print("ELEMENT NOT FOUND")
            return 1
        d = json.loads(rect)
        print(f"target: {d}")
        if d["w"] > 400:
            print("still too big — the real button is elsewhere")
            return 1
        for typ in ("mousePressed", "mouseReleased"):
            c.call("Input.dispatchMouseEvent", {
                "type": typ, "x": d["x"], "y": d["y"],
                "button": "left", "clickCount": 1})
        print("mouse click dispatched")
        for i in range(8):
            time.sleep(5)
            try:
                st = c.eval(JS_STATE, timeout=10)
                print(f"[{(i + 1) * 5}s]", st[:250])
                if json.loads(st).get("connected"):
                    print("VPN CONNECTED!")
                    return 0
            except Exception as e:
                print(f"[{(i + 1) * 5}s] eval: {type(e).__name__}")
        return 2
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
