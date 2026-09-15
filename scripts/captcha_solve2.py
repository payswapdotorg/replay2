#!/usr/bin/env python3
"""captcha_solve2.py — screenshot-based Aliyun slider solver (canvas-free).

Same drag logic as captcha_solve.py, but the gap is detected from a CDP
Page.captureScreenshot clip of the captcha image box (the 2026-09-15 auth
page taints the canvas → SecurityError on the original tool's readback).
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


def geometry(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const g = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  return JSON.stringify({
    slider: g('#aliyunCaptcha-sliding-slider'),
    track: g('#aliyunCaptcha-sliding-body'),
    imgbox: g('#aliyunCaptcha-img-box'),
    piece: g('#aliyunCaptcha-puzzle'),
    win: g('#aliyunCaptcha-window-popup')
  });
})()""", await_promise=False))


def gap_from_screenshot(cdp, imgbox, piece):
    """Capture the captcha image region and find the gap by column
    edge-energy, excluding the piece's column band."""
    clip = {"x": imgbox["x"], "y": imgbox["y"],
            "width": imgbox["w"], "height": imgbox["h"], "scale": 1}
    shot = cdp.call("Page.captureScreenshot",
                    {"format": "png", "clip": clip}, timeout=30)
    png = base64.b64decode(shot["data"])
    img = Image.open(io.BytesIO(png)).convert("L")
    a = np.asarray(img, dtype=np.float32)
    # column energy: sum of |d/dx| over rows
    de = np.abs(np.diff(a, axis=1)).sum(axis=0)  # len = w-1
    cols = np.arange(1, imgbox["w"])
    # exclude the piece band (+/- a margin) and the left startup zone
    piece_off = piece["x"] - imgbox["x"]
    margin = max(18, int(piece["w"] * 0.6))
    lo, hi = max(8, piece_off - margin), min(imgbox["w"] - 8, piece_off + piece["w"] + margin)
    mask = (cols >= lo) & (cols <= hi)
    score = np.where(mask, -1.0, de)
    # smooth: consider the best column's local 3-window sum
    win = score[:-2] + score[1:-1] + score[2:]
    gap_col = int(np.argmax(win)) + 1
    return gap_col, score


def human_drag(cdp, sx, sy, dx):
    """Press, smoothstep-eased drag with y-jitter, release (CDP mouse)."""
    steps = max(18, int(dx / 6))
    cdp.call("Input.dispatchMouseEvent",
             {"type": "mousePressed", "x": sx, "y": sy, "button": "left",
              "clickCount": 1}, timeout=15)
    t0 = time.time()
    for i in range(1, steps + 1):
        u = i / steps
        ease = u * u * (3 - 2 * u)  # smoothstep
        x = sx + dx * ease + (np.random.uniform(-0.8, 0.8) if i < steps else 0)
        y = sy + np.random.uniform(-1.2, 1.2) * (1 - u)
        cdp.call("Input.dispatchMouseEvent",
                 {"type": "mouseMoved", "x": x, "y": y, "button": "left"},
                 timeout=15)
        time.sleep(np.random.uniform(0.008, 0.02))
    # small overshoot + settle back (human-like)
    cdp.call("Input.dispatchMouseEvent",
             {"type": "mouseMoved", "x": sx + dx + 3, "y": sy, "button": "left"}, timeout=15)
    time.sleep(0.05)
    cdp.call("Input.dispatchMouseEvent",
             {"type": "mouseMoved", "x": sx + dx, "y": sy, "button": "left"}, timeout=15)
    time.sleep(0.12)
    cdp.call("Input.dispatchMouseEvent",
             {"type": "mouseReleased", "x": sx + dx, "y": sy, "button": "left",
              "clickCount": 1}, timeout=15)
    return time.time() - t0


def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else "chat.z.ai/auth"
    forced = int(sys.argv[2]) if len(sys.argv) > 2 else None
    tab = find_tab(pat)
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    geo = geometry(c)
    if not geo.get("slider"):
        print("no slider present (captcha may be gone):", json.dumps(geo))
        return 0
    if forced is not None:
        gap = forced
    else:
        gap, _ = gap_from_screenshot(c, geo["imgbox"], geo["piece"])
        # convert image-column gap to a drag distance: the piece starts at
        # its current offset; dragging moves it 1:1 — target gap minus start
    start_off = geo["piece"]["x"] - geo["imgbox"]["x"]
    drag = gap - start_off
    print(f"geometry: piece@{start_off}px gap@{gap}px -> drag {drag}px")
    if drag <= 4:
        print("drag too small — gap detection suspicious; abort");
        return 1
    sx = geo["slider"]["x"] + geo["slider"]["w"] / 2
    sy = geo["slider"]["y"] + geo["slider"]["h"] / 2
    dur = human_drag(c, sx, sy, drag)
    print(f"dragged {drag}px in {dur:.2f}s — verifying")
    time.sleep(2.5)
    geo2 = geometry(c)
    gone = (not geo2.get("slider")) or (not geo2.get("win"))
    moved = geo2.get("piece") and (geo2["piece"]["x"] - geo["imgbox"]["x"]) > start_off + 10
    print("result:", "SUCCESS (captcha gone)" if gone else ("MOVED but present (retry?)" if moved else "RESET (failed)"))
    return 0 if gone else 1


if __name__ == "__main__":
    sys.exit(main())
