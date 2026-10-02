#!/usr/bin/env python3
"""captcha_atomic.py — atomic VLM-grid-measured captcha solve loop.

For each round: fresh geometry -> grid closeup -> VLM reads gap bounds ->
compute element target so the SHAPE CENTER aligns with the GAP CENTER ->
slow human drag -> outcome check. Up to N rounds.
"""
import sys, json, time, io, base64, subprocess
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
import captcha_solve2 as cs
import captcha_solve as orig
from PIL import Image, ImageDraw

VLM_PROMPT = (
    "This captcha image has red vertical gridlines every 50 pixels labeled 0,50,100...550 in yellow. "
    "A semi-transparent puzzle piece shape sits near the LEFT edge. Right of it is the GAP/hole (dark "
    "notch) where the piece must be dragged. Read the rulers and answer with NUMBERS ONLY: "
    "1) gap_left_px 2) gap_right_px 3) piece_shape_left_px 4) piece_shape_right_px"
)

def vlm_grid(c, imgbox):
    clip = {"x": imgbox["x"], "y": imgbox["y"], "width": imgbox["w"], "height": imgbox["h"], "scale": 2}
    shot = c.call("Page.captureScreenshot", {"format": "png", "clip": clip}, timeout=30)
    img = Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB")
    d = ImageDraw.Draw(img)
    for x in range(0, img.size[0], 50):
        d.line([(x, 0), (x, img.size[1])], fill=(255, 0, 0), width=2)
        d.text((x + 3, 5), str(x), fill=(255, 255, 0))
    img.save('/tmp/captcha_atomic_grid.png')
    out = subprocess.run(
        ["z-ai", "vision", "-p", VLM_PROMPT, "-i", "/tmp/captcha_atomic_grid.png"],
        capture_output=True, text=True, timeout=120, cwd="/home/z/my-project").stdout
    start = out.find('{')
    if start < 0:
        return None
    try:
        content = json.loads(out[start:])['choices'][0]['message']['content']
    except Exception:
        return None
    import re
    nums = [float(m) for m in re.findall(r'\d+(?:\.\d+)?', content)]
    if len(nums) >= 4:
        return {"gap_l": nums[0]/2, "gap_r": nums[1]/2, "pc_l": nums[2]/2, "pc_r": nums[3]/2}
    return None

def click(c, x, y):
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)
    time.sleep(0.1)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, timeout=15)

def close_stale(c):
    el = json.loads(c.eval(r"""(() => {
      const b = document.querySelector('#aliyunCaptcha-btn-close');
      if (!b) return 'null';
      const r = b.getBoundingClientRect();
      return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
    })()""", await_promise=False))
    if el and el != 'null':
        e = json.loads(el) if isinstance(el, str) else el
        click(c, e["x"], e["y"])
        time.sleep(1.2)
        return True
    return False

def ensure_captcha(c):
    geo = cs.geometry(c)
    if geo.get("slider") and geo["slider"]["w"] > 0:
        return geo
    el = json.loads(c.eval(r"""(() => {
      const cands = [...document.querySelectorAll('button, div[role=button], span, div')].filter(x => (x.innerText||'').trim() === 'Click to start verification' && x.children.length <= 2);
      if (!cands.length) return 'null';
      const r = cands[cands.length-1].getBoundingClientRect();
      return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
    })()""", await_promise=False))
    if el and el != 'null':
        e = json.loads(el) if isinstance(el, str) else el
        click(c, e["x"], e["y"])
        time.sleep(2.5)
    return cs.geometry(c)

def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    tab = cs.find_tab("chat.z.ai")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=90)
    close_stale(c)
    for rnd in range(1, rounds + 1):
        geo = ensure_captcha(c)
        if not (geo.get("slider") and geo["slider"]["w"] > 0):
            print(f"round {rnd}: no live captcha"); time.sleep(2); continue
        m = vlm_grid(c, geo["imgbox"])
        if not m:
            print(f"round {rnd}: VLM measure failed"); close_stale(c); continue
        gap_c = (m["gap_l"] + m["gap_r"]) / 2
        shape_c = (m["pc_l"] + m["pc_r"]) / 2
        start_off = geo["piece"]["x"] - geo["imgbox"]["x"]
        # element.x = E: shape lands at E + shape_c. want E + shape_c = gap_c
        target_E = gap_c - shape_c
        drag = target_E - start_off
        print(f"round {rnd}: gap[{m['gap_l']:.0f},{m['gap_r']:.0f}]c={gap_c:.1f} shape_c={shape_c:.1f} start={start_off} -> element target {target_E:.1f}, drag {drag:.1f}px")
        if not (15 <= drag <= 262):
            print("  drag out of range — remeasure"); close_stale(c); continue
        sx = geo["slider"]["x"] + geo["slider"]["w"] / 2
        sy = geo["slider"]["y"] + geo["slider"]["h"] / 2
        orig.drag(c, sx, sy, drag, steps=48, dwell=2.2)
        time.sleep(2.5)
        o = orig.outcome(c)
        solved = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
        print(f"  outcome: solved={solved} tail={o['tail'][-80:]!r}")
        if solved:
            print("SOLVED")
            return 0
        close_stale(c)
        time.sleep(1.0)
    print("EXHAUSTED ROUNDS")
    return 1

if __name__ == "__main__":
    sys.exit(main())
