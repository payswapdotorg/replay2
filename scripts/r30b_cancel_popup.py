#!/usr/bin/env python3
"""r30b_cancel_popup.py — cancel the capacity popup on the worker chat
(operator rule: NEVER 'Switch to GLM-5.3-Flash'; Cancel + resend)."""
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS_CANCEL = """
(() => {
  const btns = [...document.querySelectorAll('button')];
  const cancel = btns.find(b => (b.innerText || '').trim() === 'Cancel');
  if (!cancel) return 'no-cancel-button';
  const r = cancel.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()
"""

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({popup: t.includes('Switch to GLM-5.3-Flash'),
                         noResp: t.includes('No response')});
})()
"""


def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else "dd5c60bf"
    tabs = [t for t in channel.list_tabs() if sub in (t.get("url") or "")]
    if not tabs:
        print("NOTAB")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
    try:
        r = c.eval(JS_CANCEL, timeout=12)
        print("cancel button:", r)
        if r in ("no-cancel-button",):
            return 1
        import json
        d = json.loads(r)
        for typ in ("mousePressed", "mouseReleased"):
            c.call("Input.dispatchMouseEvent", {
                "type": typ, "x": d["x"], "y": d["y"],
                "button": "left", "clickCount": 1})
        print("Cancel clicked (real mouse)")
        time.sleep(3)
        st = c.eval(JS_STATE, timeout=10)
        print("state after:", st)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
