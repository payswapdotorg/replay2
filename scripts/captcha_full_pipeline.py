#!/usr/bin/env python3
"""captcha_full_pipeline.py — the complete login-assist in ONE process:
close stale challenge -> click Sign in (spawns fresh captcha; fallback: click
start-verification) -> screenshot -> VLM gap detection (gridlined) -> drag ->
immediate Sign-in if needed. Every step in-process to beat the certify TTL."""
import sys, time, json, base64, subprocess
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
import captcha_solve2 as cs
import importlib.util

spec = importlib.util.spec_from_file_location("orig", "/home/z/replay2/scripts/captcha_solve.py")
orig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orig)

CAP_IMG = "/home/z/my-project/captcha_now.png"
GRID_IMG = "/home/z/my-project/captcha_now_grid.png"
VLM_OUT = "/tmp/vlm_now.json"


def click(c, x, y):
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)
    time.sleep(0.06)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)


def el_center(c, js):
    return json.loads(c.eval(js, await_promise=False))


JS_CLOSE = r"""(() => {
  const b = document.querySelector('#aliyunCaptcha-btn-close');
  if (!b) return JSON.stringify(null);
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
})()"""

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


def captcha_geo(c):
    g = cs.geometry(c)
    return g if (g.get("slider") and g["slider"]["w"] > 0) else None


def vlm_gap(c, geo):
    """Screenshot + gridlines + z-ai vision -> gap css px (int) or None."""
    from PIL import Image, ImageDraw
    x = min(geo["imgbox"]["x"], geo["track"]["x"])
    y = geo["imgbox"]["y"]
    w = max(geo["imgbox"]["w"], geo["track"]["w"])
    h = (geo["track"]["y"] + geo["track"]["h"]) - geo["imgbox"]["y"]
    shot = c.call("Page.captureScreenshot",
                  {"format": "png", "clip": {"x": x, "y": y, "width": w, "height": h, "scale": 2}}, timeout=30)
    open(CAP_IMG, "wb").write(base64.b64decode(shot["data"]))
    img = Image.open(CAP_IMG).convert("RGB")
    d = ImageDraw.Draw(img)
    iw, ih = img.size
    for gx in range(0, iw, 60):
        d.line([(gx, 0), (gx, ih)], fill=(255, 0, 0), width=1)
        d.text((gx + 2, 2), str(gx // 2), fill=(255, 255, 0))
    img.save(GRID_IMG)
    prompt = ("This captcha screenshot has RED vertical gridlines every 30 CSS pixels with YELLOW numbers "
              "showing CSS x coordinates. A vertical slice of the picture was cut and placed at the LEFT edge. "
              "Find the vertical band to the RIGHT where the image is cut/missing/misaligned — where the slice "
              "must be dragged. Answer ONLY JSON: {\"gap_left_css_px\": <number>}.")
    r = subprocess.run(["z-ai", "vision", "-p", prompt, "-i", GRID_IMG, "-o", VLM_OUT],
                       capture_output=True, text=True, timeout=90, cwd="/home/z/my-project")
    try:
        d = json.load(open(VLM_OUT))
        content = d["choices"][0]["message"]["content"]
        m = json.loads(content[content.find("{"):content.rfind("}") + 1])
        return int(m["gap_left_css_px"])
    except Exception as e:
        print("VLM parse failed:", str(e)[:80], "| raw:", r.stdout[-100:] if r.stdout else "")
        return None


def main():
    tab = cs.find_tab("chat.z.ai/auth")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)

    # 0) close any stale challenge popup
    b = el_center(c, JS_CLOSE)
    if b:
        print("closing stale popup:", b)
        click(c, b["x"], b["y"])
        time.sleep(1.5)

    # 1) click Sign in — spawns the captcha with a fresh certify token
    b = el_center(c, JS_SIGNIN)
    if b and not b["disabled"]:
        print("clicking Sign in:", b)
        click(c, b["x"], b["y"])
    time.sleep(2.0)

    # 1b) fallback: click start-verification if no captcha spawned
    geo = captcha_geo(c)
    if not geo:
        s = el_center(c, JS_START)
        if s:
            print("captcha not spawned by Sign in; clicking start-verification:", s)
            click(c, s["x"], s["y"])
            time.sleep(2.5)
            geo = captcha_geo(c)
    if not geo:
        href = c.eval("location.href", await_promise=False)
        print("no captcha live; url:", href)
        return 0 if "/auth" not in href else 1

    # 2) VLM gap detection (fast, in-process subprocess)
    gap = vlm_gap(c, geo)
    piece_off = geo["piece"]["x"] - geo["imgbox"]["x"]
    if gap is None:
        print("VLM failed — aborting without drag (captcha stays armed)")
        return 1
    drag_px = gap - piece_off
    print(f"VLM gap@{gap} piece@{piece_off} -> drag {drag_px}px")

    # 3) drag immediately
    hx = geo["slider"]["x"] + geo["slider"]["w"] / 2
    hy = geo["slider"]["y"] + geo["slider"]["h"] / 2
    orig.drag(c, hx, hy, drag_px)

    # 4) verify + immediate Sign-in if still on auth
    time.sleep(2.5)
    href = c.eval("location.href", await_promise=False)
    if "/auth" not in href:
        print("*** LOGIN PROCEEDED ***", href)
        return 0
    o = orig.outcome(c)
    gone = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
    print("outcome:", json.dumps(o)[:160])
    if gone:
        b = el_center(c, JS_SIGNIN)
        if b and not b["disabled"]:
            print("captcha cleared -> clicking Sign in NOW:", b)
            click(c, b["x"], b["y"])
            time.sleep(8)
            href = c.eval("location.href", await_promise=False)
            body = c.eval("document.body.innerText.slice(0,200)", await_promise=False)
            print("url:", href)
            print("body:", body.replace("\n", " | ")[:180])
            if "/auth" not in href:
                print("*** LOGIN PROCEEDED ***")
                return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
