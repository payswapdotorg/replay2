#!/usr/bin/env python3
"""captcha_retry.py — click start-verification, solve with the ORIGINAL house
drag trajectory (42 steps / 2.6s dwell), report outcome."""
import sys, time, json
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
import captcha_solve2 as cs
import importlib.util

spec = importlib.util.spec_from_file_location("orig", "/home/z/replay2/scripts/captcha_solve.py")
orig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orig)

JS_START = r"""(() => {
  const cands = [...document.querySelectorAll('button, div[role=button], span, div')].filter(x => (x.innerText||'').trim() === 'Click to start verification' && x.children.length <= 2);
  if (!cands.length) return JSON.stringify(null);
  const r = cands[cands.length-1].getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
})()"""


def click(c, x, y):
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)
    time.sleep(0.08)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)


def main():
    tab = cs.find_tab("chat.z.ai/auth")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    geo = cs.geometry(c)
    live = geo.get("slider") and geo["slider"]["w"] > 0
    if not live:
        el = json.loads(c.eval(JS_START, await_promise=False))
        print("restart captcha:", el)
        if el:
            click(c, el["x"], el["y"])
            time.sleep(3)
        geo = cs.geometry(c)
        live = geo.get("slider") and geo["slider"]["w"] > 0
    if not live:
        print("NO CAPTCHA LIVE — page may be past verification")
        body = c.eval("document.body.innerText.slice(0,200)", await_promise=False)
        print("body:", body.replace("\n", " | ")[:180])
        return 1
    gap, _ = cs.gap_from_screenshot(c, geo["imgbox"], geo["piece"])
    piece_left = geo["piece"]["x"] - geo["imgbox"]["x"]
    drag_px = gap - piece_left
    print(f"gap@{gap} piece@{piece_left} -> drag {drag_px}px (original slow drag)")
    hx = geo["slider"]["x"] + geo["slider"]["w"] / 2
    hy = geo["slider"]["y"] + geo["slider"]["h"] / 2
    orig.drag(c, hx, hy, drag_px)
    time.sleep(3)
    o = orig.outcome(c)
    print("outcome:", json.dumps(o)[:250])
    solved = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
    print("VERDICT:", "SOLVED" if solved else "STILL PRESENT")
    return 0 if solved else 1


if __name__ == "__main__":
    sys.exit(main())
