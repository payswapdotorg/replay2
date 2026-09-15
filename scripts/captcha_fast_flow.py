#!/usr/bin/env python3
"""captcha_fast_flow.py <drag_px> — the complete login-assist sequence in ONE
fast script: close-retry if present -> Sign in (spawns fresh captcha) -> wait
for slider -> drag immediately (cached gap px; same CertifyId = same image)
-> verify + click Sign in if needed. Minimizes the certify-token TTL waste."""
import sys, time, json
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
import captcha_solve2 as cs
import importlib.util

spec = importlib.util.spec_from_file_location("orig", "/home/z/replay2/scripts/captcha_solve.py")
orig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orig)

JS_ANY_BUTTON = r"""(() => {
  const want = %ARGS%;
  for (const w of want) {
    const b = [...document.querySelectorAll('button, a, div[role=button], span')].find(x => (x.innerText||'').trim().toLowerCase() === w && x.offsetParent !== null);
    if (b) { const r = b.getBoundingClientRect(); return JSON.stringify({match: w, x: r.x + r.width/2, y: r.y + r.height/2}); }
  }
  return JSON.stringify(null);
})()"""


def find_button(c, names):
    js = JS_ANY_BUTTON.replace("%ARGS%", json.dumps(names))
    return json.loads(c.eval(js, await_promise=False))


def click(c, x, y):
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)
    time.sleep(0.06)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)


def captcha_live(c):
    g = cs.geometry(c)
    return g if (g.get("slider") and g["slider"]["w"] > 0) else None


def main():
    drag_px = float(sys.argv[1])
    tab = cs.find_tab("chat.z.ai/auth")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)

    # 0) clear a timed-out challenge if present
    b = find_button(c, ["close and retry", "retry"])
    if b:
        print("closing stale challenge:", b)
        click(c, b["x"], b["y"])
        time.sleep(1.5)

    # 1) click Sign in (spawns/arms the captcha with a fresh certify token)
    b = find_button(c, ["sign in"])
    if not b:
        print("no Sign in button"); return 1
    print("clicking Sign in:", b)
    click(c, b["x"], b["y"])

    # 2) wait for the slider to spawn (fast poll)
    geo = None
    for _ in range(24):
        time.sleep(0.7)
        geo = captcha_live(c)
        if geo:
            break
    if not geo:
        # maybe login proceeded without captcha
        href = c.eval("location.href", await_promise=False)
        print("no captcha after sign-in; url:", href)
        if "/auth" not in href:
            print("LOGIN PROCEEDED WITHOUT CAPTCHA")
            return 0
        return 1
    print("captcha live; dragging %.0fpx immediately" % drag_px)
    hx = geo["slider"]["x"] + geo["slider"]["w"] / 2
    hy = geo["slider"]["y"] + geo["slider"]["h"] / 2
    orig.drag(c, hx, hy, drag_px)

    # 3) verify outcome fast
    for _ in range(8):
        time.sleep(1.2)
        o = orig.outcome(c)
        gone = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
        if gone:
            break
    print("outcome:", json.dumps(o)[:180])
    href = c.eval("location.href", await_promise=False)
    body = c.eval("document.body.innerText.slice(0,250)", await_promise=False)
    print("url:", href)
    print("body:", body.replace("\n", " | ")[:220])
    if "/auth" not in href:
        print("*** LOGIN PROCEEDED ***")
        return 0
    # 4) captcha cleared but still on auth? click Sign in once more, fast
    if gone:
        b = find_button(c, ["sign in"])
        if b:
            print("captcha cleared; clicking Sign in again:", b)
            click(c, b["x"], b["y"])
            time.sleep(8)
            href = c.eval("location.href", await_promise=False)
            body = c.eval("document.body.innerText.slice(0,250)", await_promise=False)
            print("url:", href)
            print("body:", body.replace("\n", " | ")[:220])
            if "/auth" not in href:
                print("*** LOGIN PROCEEDED ***")
                return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
