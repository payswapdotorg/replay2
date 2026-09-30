#!/usr/bin/env python3
"""captcha_solve.py <session_url_substr> [drag_px] — solve the Aliyun slider
captcha via CDP input events.

Locates the captcha elements (#aliyunCaptcha-sliding-slider handle,
#aliyunCaptcha-img-box background), drags the handle with a human-like
trajectory (smoothstep easing + y-jitter), then reports the outcome
(mask/window gone = success; slider reset = fail).

If drag_px is omitted, the gap is auto-detected from the background image
via column edge-energy analysis (excluding the piece region on the left).
"""
import base64
import io
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def find_tab(pat):
    for x in channel.list_tabs():
        if pat in x.get("url", ""):
            return x
    raise SystemExit(f"no tab matches {pat}")


def captcha_geometry(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const g = (id) => {
    const el = document.querySelector('#' + id);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: r.x, y: r.y, w: r.width, h: r.height};
  };
  return JSON.stringify({
    mask: g('aliyunCaptcha-mask'),
    win: g('aliyunCaptcha-window-popup'),
    imgbox: g('aliyunCaptcha-img-box'),
    slider: g('aliyunCaptcha-sliding-slider'),
    track: g('aliyunCaptcha-sliding-body'),
    piece: g('aliyunCaptcha-puzzle')
  });
})()"""))


def bg_gap_x(cdp):
    """Auto-detect the gap left edge (display px within the 300px image)."""
    b64 = cdp.eval(r"""(() => {
  const b = document.querySelector('#aliyunCaptcha-img');
  const cn = document.createElement('canvas');
  cn.width = b.naturalWidth; cn.height = b.naturalHeight;
  const ctx = cn.getContext('2d');
  ctx.drawImage(b, 0, 0);
  return cn.toDataURL('image/png').split(',')[1];
})()""", timeout=30)
    arr = np.array(Image.open(io.BytesIO(base64.b64decode(b64))).convert("L"), dtype=float)
    h, w = arr.shape
    scale = 300.0 / w
    grad = np.abs(np.diff(arr, axis=1))
    col_energy = grad.sum(axis=0)
    region = col_energy[int(60 / scale):]
    k = 5
    smooth = np.convolve(region, np.ones(k) / k, mode="same")
    top = np.argsort(smooth)[::-1][:8]
    cols = sorted(int(c + int(60 / scale)) for c in top)
    # left cluster = gap left edge
    left = [c for c in cols if c < cols[0] + 8]
    gap_left_nat = sum(left) / len(left)
    return gap_left_nat * scale, [round(c * scale, 1) for c in cols]


def drag(cdp, x0, y0, dx, steps=42, dwell=2.6):
    cdp.call("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": x0, "y": y0, "button": "left",
        "buttons": 1, "clickCount": 1})
    dt = dwell / steps
    for i in range(1, steps + 1):
        p = i / steps
        ease = p * p * (3 - 2 * p)  # smoothstep
        x = x0 + dx * ease
        y = y0 + 2.5 * ((i % 5) - 2) / 2.0  # small y jitter
        cdp.call("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": round(x, 1), "y": round(y, 1),
            "button": "left", "buttons": 1})
        time.sleep(dt)
    time.sleep(0.25)
    cdp.call("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": round(x0 + dx, 1), "y": y0,
        "button": "left", "buttons": 0, "clickCount": 1})


def outcome(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const mask = document.querySelector('#aliyunCaptcha-mask');
  const win = document.querySelector('#aliyunCaptcha-window-popup');
  const body = document.body.innerText || '';
  return JSON.stringify({
    maskShown: !!(mask && mask.className && String(mask.className).includes('mask-show')),
    winShown: !!(win && win.className && String(win.className).includes('window-show')),
    winRect: win ? (r => ({x: r.x, y: r.y, w: r.width, h: r.height}))(win.getBoundingClientRect()) : null,
    hasCaptcha: body.includes('drag the slider') || body.includes('security verification'),
    tail: body.slice(-200)
  });
})()"""))


def main():
    pat = sys.argv[1]
    drag_px = float(sys.argv[2]) if len(sys.argv) > 2 else None
    t = find_tab(pat)
    cdp = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        g = captcha_geometry(cdp)
        if not g["slider"] or not g["track"]:
            print("NO CAPTCHA PRESENT:", json.dumps(g))
            return
        print("geometry:", json.dumps(g))
        if drag_px is None:
            gap, cols = bg_gap_x(cdp)
            print(f"auto gap-left={gap:.1f} (energy cols {cols})")
            piece_left = g["piece"]["x"] - g["imgbox"]["x"] if g["piece"] and g["imgbox"] else 0
            drag_px = gap - piece_left
        print(f"dragging {drag_px:.1f}px")
        hx = g["slider"]["x"] + g["slider"]["w"] / 2
        hy = g["slider"]["y"] + g["slider"]["h"] / 2
        drag(cdp, hx, hy, drag_px)
        time.sleep(3)
        o = outcome(cdp)
        print("outcome:", json.dumps(o))
        if not o["maskShown"] and not o["winShown"]:
            print("SOLVED — captcha window closed")
        else:
            print("STILL PRESENT — likely failed; slider may have reset")
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
