#!/usr/bin/env python3
"""captcha_exec.py — fast captcha execution with a PRE-COMPUTED gap.
The bg/piece images are stable per login session (verified by checksum), so
the gap analysis can happen offline; this script only spawns + drags + signs
in, well within the certify TTL. Retries with offset ladder on failure."""
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
    time.sleep(0.06)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)


def try_once(c, drag_px, do_signin=True):
    """spawn -> drag -> verify -> sign in. Returns 'LOGIN' | 'SOLVED' | 'FAIL'."""
    geo = cs.geometry(c)
    if not (geo.get("slider") and geo["slider"]["w"] > 0):
        s = json.loads(c.eval(JS_START, await_promise=False))
        if not s:
            href = c.eval("location.href", await_promise=False)
            if "/auth" not in href:
                return "LOGIN"
            return "FAIL"
        click(c, s["x"], s["y"])
        for _ in range(16):
            time.sleep(0.6)
            geo = cs.geometry(c)
            if geo.get("slider") and geo["slider"]["w"] > 0:
                break
        if not (geo.get("slider") and geo["slider"]["w"] > 0):
            return "FAIL"
    hx = geo["slider"]["x"] + geo["slider"]["w"] / 2
    hy = geo["slider"]["y"] + geo["slider"]["h"] / 2
    orig.drag(c, hx, hy, drag_px)
    time.sleep(2.2)
    o = orig.outcome(c)
    gone = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
    href = c.eval("location.href", await_promise=False)
    if "/auth" not in href:
        return "LOGIN"
    if gone and do_signin:
        b = json.loads(c.eval(JS_SIGNIN, await_promise=False))
        if b and not b["disabled"]:
            click(c, b["x"], b["y"])
            time.sleep(8)
            href = c.eval("location.href", await_promise=False)
            if "/auth" not in href:
                return "LOGIN"
        return "SOLVED"
    return "FAIL"


def main():
    base = float(sys.argv[1])
    offsets = [0, -3, 3, -6, 6, -9, 9, -12, 12]
    tab = cs.find_tab("chat.z.ai/auth")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    for off in offsets:
        drag = base + off
        r = try_once(c, drag)
        print(f"drag {drag:.0f}px -> {r}", flush=True)
        if r == "LOGIN":
            href = c.eval("location.href", await_promise=False)
            body = c.eval("document.body.innerText.slice(0,200)", await_promise=False)
            print("*** LOGIN PROCEEDED ***", href)
            print("body:", body.replace("\n", " | ")[:180])
            return 0
        if r == "SOLVED":
            print("captcha solved but login did not proceed — stopping for inspection")
            return 2
        time.sleep(1.5)
    print("offset ladder exhausted")
    return 4


if __name__ == "__main__":
    sys.exit(main())
