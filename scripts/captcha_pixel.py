#!/usr/bin/env python3
"""captcha_pixel.py — pure-pixel atomic captcha solver.

Per round: fresh geometry -> @2x screenshot -> piece-shape extent (std) ->
gap = dark-run cluster (excluding right border) + dip fragment -> slow drag
so shape-center meets gap-center -> outcome. Retry loop.
"""
import sys, json, time, io, base64
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

def analyze(c, geo):
    """Returns (drag_px, detail) or (None, reason)."""
    ib, pc = geo["imgbox"], geo["piece"]
    clip = {"x": ib["x"], "y": ib["y"], "width": ib["w"], "height": ib["h"], "scale": 2}
    shot = c.call("Page.captureScreenshot", {"format": "png", "clip": clip}, timeout=30)
    a = np.asarray(Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("L"), dtype=np.float32)
    h, w = a.shape
    piece_w2x = pc["w"] * 2
    # piece shape extent inside element zone
    stds = a[:, :piece_w2x].std(axis=0)
    shape_cols = [x for x in range(piece_w2x) if stds[x] > 4]
    if not shape_cols:
        return None, "no shape cols"
    pc_l, pc_r = min(shape_cols), max(shape_cols)
    shape_center = (pc_l + pc_r) / 2 / 2  # logical
    # dark-run clusters
    def longest_run(col, thresh=115):
        best = cur = 0
        for v in col:
            if v < thresh:
                cur += 1; best = max(best, cur)
            else:
                cur = 0
        return best
    runs = np.array([longest_run(a[:, x]) for x in range(w)])
    dark_cols = [x for x in range(piece_w2x + 20, w - 12) if runs[x] > 40]
    # exclude border cluster: within 14px of right edge
    dark_cols = [x for x in dark_cols if x < w - 14]
    # dip fragments
    mid = a[150:450, :]
    colmean = mid.mean(axis=0)
    k = 15
    sm = np.convolve(colmean, np.ones(k)/k, mode='same')
    dip_cols = [x for x in range(piece_w2x + 20, w - 12) if sm[x] < sm.max() - 45]
    detail = {"shape": [pc_l, pc_r], "dark": dark_cols[:20], "dip": dip_cols[:20]}
    if not dark_cols:
        return None, f"no dark cluster {detail}"
    # cluster = contiguous dark cols (allow gaps <= 6)
    clusters = []
    cur = [dark_cols[0]]
    for x in dark_cols[1:]:
        if x - cur[-1] <= 6:
            cur.append(x)
        else:
            clusters.append(cur); cur = [x]
    clusters.append(cur)
    # choose the cluster with the longest total run sum
    best_cl = max(clusters, key=lambda cl: sum(runs[x] for x in cl))
    gap_right2x = max(best_cl)
    gap_left2x = gap_right2x - (pc_r - pc_l)
    # if a dip fragment lies just left of the cluster, refine gap_left
    for dx in dip_cols:
        if gap_left2x - 30 <= dx <= gap_right2x:
            gap_left2x = min(gap_left2x, dx)
            break
    gap_c = (gap_left2x + gap_right2x) / 2 / 2  # logical center
    start_off = pc["x"] - ib["x"]
    target_E = gap_c - shape_center
    drag = target_E - start_off
    detail.update({"gap2x": [gap_left2x, gap_right2x], "gap_c": round(gap_c,1), "shape_center": round(shape_center,1), "target_E": round(target_E,1), "drag": round(drag,1)})
    return drag, detail

def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    tab = cs.find_tab("chat.z.ai")
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=90)
    close_stale(c)
    for rnd in range(1, rounds + 1):
        geo = ensure_captcha(c)
        if not (geo.get("slider") and geo["slider"]["w"] > 0):
            print(f"round {rnd}: no live captcha"); time.sleep(2); continue
        drag, detail = analyze(c, geo)
        print(f"round {rnd}: drag={drag} detail={json.dumps(detail)}")
        if drag is None or not (15 <= drag <= 262):
            print("  invalid drag — closing and retrying"); close_stale(c); time.sleep(1); continue
        sx = geo["slider"]["x"] + geo["slider"]["w"] / 2
        sy = geo["slider"]["y"] + geo["slider"]["h"] / 2
        orig.drag(c, sx, sy, drag, steps=48, dwell=2.2)
        time.sleep(2.5)
        o = orig.outcome(c)
        solved = not o["maskShown"] and not o["winShown"] and not o["hasCaptcha"]
        print(f"  outcome solved={solved} tail={o['tail'][-60:]!r}")
        if solved:
            print("SOLVED")
            return 0
        close_stale(c); time.sleep(1)
    print("EXHAUSTED")
    return 1

if __name__ == "__main__":
    sys.exit(main())
