#!/usr/bin/env python3
"""captcha_drag_n_signin.py <drag_px> — drag the slider by exact px with the
original house trajectory, then click Sign in if the captcha clears."""
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

JS_SIGNIN = r"""(() => {
  const b = [...document.querySelectorAll('button')].find(x => (x.innerText||'').trim() === 'Sign in');
  if (!b) return JSON.stringify(null);
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2, disabled: b.disabled});
})()"""


def click(c, x, y):
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)
    time.sleep(0.08)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)


def main():
    drag_px = float(sys.argv[1])
    tab = cs.find_tab("chat.z.ai/auth")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    geo = cs.geometry(c)
    if not (geo.get("slider") and geo["slider"]["w"] > 0):
        el = json.loads(c.eval(JS_START, await_promise=False))
        print("captcha not live; clicking start:", el)
        if el:
            click(c, el["x"], el["y"])
            time.sleep(3)
        geo = cs.geometry(c)
        if not (geo.get("slider") and geo["slider"]["w"] > 0):
            print("captcha still not live — abort")
            return 1
    hx = geo["slider"]["x"] + geo["slider"]["w"] / 2
    hy = geo["slider"]["y"] + geo["slider"]["h"] / 2
    print(f"dragging {drag_px}px from ({hx},{hy})")
    orig.drag(c, hx, hy, drag_px)
    time.sleep(3)
    o = orig.outcome(c)
    print("outcome:", json.dumps(o)[:200])
    solved = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
    print("VERDICT:", "SOLVED" if solved else "STILL PRESENT")
    if solved:
        btn = json.loads(c.eval(JS_SIGNIN, await_promise=False))
        print("sign-in btn:", btn)
        if btn and not btn["disabled"]:
            click(c, btn["x"], btn["y"])
            print("clicked Sign in")
            time.sleep(8)
            href = c.eval("location.href", await_promise=False)
            body = c.eval("document.body.innerText.slice(0,200)", await_promise=False)
            print("FINAL url:", href)
            print("FINAL body:", body.replace("\n", " | ")[:180])
    return 0 if solved else 1


if __name__ == "__main__":
    sys.exit(main())
