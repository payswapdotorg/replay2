#!/usr/bin/env python3
"""captcha_imagesolver.py — exact solver using the captcha's own images.

Reads the live DOM image URLs, downloads bg (inpainted_with_mask) + piece
(bitwise_and_result), finds the piece band via alpha, finds the inpainted
gap (lowest-variance window of piece-width over the band), drags the piece
element to gap-left with a slow human trajectory. Verifies outcome.
"""
import sys, json, time, io, base64, urllib.request
sys.path.insert(0, "/home/z/replay2/scripts")
import channel
import captcha_solve2 as cs
import captcha_solve as orig
from PIL import Image
import numpy as np

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
        click(c, e["x"], e["y"]); time.sleep(1.2); return True
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
        click(c, e["x"], e["y"]); time.sleep(2.5)
    return cs.geometry(c)

def get_img_urls(c):
    return json.loads(c.eval(r"""(() => {
      const bg = document.querySelector('#aliyunCaptcha-img');
      const pc = document.querySelector('#aliyunCaptcha-puzzle');
      if (!bg || !pc || !bg.src || !pc.src) return 'null';
      return JSON.stringify({bg: bg.src, pc: pc.src});
    })()""", await_promise=False))

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()

def analyze(bg_bytes, pc_bytes):
    bg = np.asarray(Image.open(io.BytesIO(bg_bytes)).convert("L"), dtype=np.float32)
    pc = np.asarray(Image.open(io.BytesIO(pc_bytes)).convert("RGBA"), dtype=np.float32)
    alpha = pc[:, :, 3]
    pcols = [x for x in range(pc.shape[1]) if (alpha[:, x] > 40).sum() > 5]
    prows = [y for y in range(pc.shape[0]) if (alpha[y, :] > 40).sum() > 5]
    if not pcols or not prows:
        return None, "no piece shape"
    pw = max(pcols) - min(pcols) + 1
    r0, r1 = min(prows), max(prows)
    # scan gap: lowest-variance window of width pw over rows [r0, r1]
    cands = []
    for x in range(pw + 10, bg.shape[1] - pw - 4):
        win = bg[r0:r1+1, x:x+pw]
        if win.shape[1] < pw: break
        cands.append((x, float(win.std())))
    if not cands:
        return None, "no scan range"
    cands.sort(key=lambda t: t[1])
    gap_x = cands[0][0]
    return {"gap_x": gap_x, "piece_w": pw, "band": [r0, r1],
            "top3": [(x, round(v,1)) for x, v in cands[:3]]}, None

def main():
    tab = cs.find_tab("chat.z.ai")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=90)
    close_stale(c)
    for rnd in range(1, 4):
        geo = ensure_captcha(c)
        if not (geo.get("slider") and geo["slider"]["w"] > 0):
            print(f"round {rnd}: no live captcha"); time.sleep(2); continue
        urls = get_img_urls(c)
        if not urls or urls == 'null':
            print(f"round {rnd}: img urls missing"); time.sleep(1); continue
        urls = json.loads(urls) if isinstance(urls, str) else urls
        try:
            bg_b, pc_b = fetch(urls["bg"]), fetch(urls["pc"])
        except Exception as e:
            print(f"round {rnd}: fetch failed {e}"); close_stale(c); continue
        info, err = analyze(bg_b, pc_b)
        if err:
            print(f"round {rnd}: analyze failed: {err}"); close_stale(c); continue
        start_off = geo["piece"]["x"] - geo["imgbox"]["x"]
        drag = info["gap_x"] - start_off
        print(f"round {rnd}: {json.dumps(info)} start_off={start_off} -> drag {drag}px")
        if not (15 <= drag <= 262):
            print("  drag out of range"); close_stale(c); time.sleep(1); continue
        sx = geo["slider"]["x"] + geo["slider"]["w"] / 2
        sy = geo["slider"]["y"] + geo["slider"]["h"] / 2
        orig.drag(c, sx, sy, drag, steps=48, dwell=2.2)
        time.sleep(2.5)
        o = orig.outcome(c)
        solved = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
        print(f"  solved={solved} tail={o['tail'][-70:]!r}")
        if solved:
            print("SOLVED")
            return 0
        close_stale(c); time.sleep(1)
    print("EXHAUSTED")
    return 1

if __name__ == "__main__":
    sys.exit(main())
