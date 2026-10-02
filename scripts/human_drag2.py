#!/usr/bin/env python3
"""human_drag2.py — realistic human drag trajectory for Aliyun sliders.

Phases: approach-hover -> press-pause -> ballistic (fast, noisy) ->
decelerate -> overshoot -> correct back -> settle -> release.
Event rate ~60-90Hz with jittered intervals; y = slow random walk.
"""
import time, random
import numpy as np

def human_drag2(cdp, sx, sy, dx, seed=None):
    rng = random.Random(seed) if seed is not None else random.Random()
    t_total = 0.0

    def mv(x, y, buttons=0):
        nonlocal t_total
        cdp.call("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": round(x, 1), "y": round(y, 1),
            "button": "none" if not buttons else "left",
            "buttons": buttons}, timeout=15)
        dt = max(0.006, rng.gauss(0.014, 0.006))
        time.sleep(dt)
        t_total += dt

    # 1) approach hover: 4-6 moves toward the slider from ~60px left
    ax = sx - rng.uniform(45, 70)
    ay = sy + rng.uniform(-6, 6)
    steps = rng.randint(4, 6)
    for i in range(1, steps + 1):
        u = i / steps
        mv(ax + (sx - ax) * u, ay + (sy - ay) * u)
    time.sleep(rng.uniform(0.15, 0.3)); t_total += 0.2

    # 2) press + hold
    cdp.call("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": round(sx, 1), "y": round(sy, 1),
        "button": "left", "buttons": 1, "clickCount": 1}, timeout=15)
    time.sleep(rng.uniform(0.08, 0.16)); t_total += 0.12

    # 3) ballistic: cover ~55-75% of dx quickly
    y = sy
    yv = rng.uniform(-0.4, 0.4)
    ball_end = dx * rng.uniform(0.55, 0.75)
    x = sx
    while x - sx < ball_end:
        v = rng.uniform(2.5, 5.5)  # px per event
        x = min(x + v, sx + ball_end)
        yv += rng.uniform(-0.15, 0.15); yv = max(-1.5, min(1.5, yv))
        y += yv
        mv(x, y, buttons=1)

    # 4) decelerate to overshoot point (target + 3..8px)
    over = rng.uniform(3, 8)
    tx = sx + dx + over
    while x < tx:
        v = max(0.6, (tx - x) * rng.uniform(0.18, 0.3))
        x = min(x + v, tx)
        yv += rng.uniform(-0.1, 0.1); yv = max(-1.2, min(1.2, yv))
        y += yv * 0.6
        mv(x, y, buttons=1)
        time.sleep(0.004)
    # brief hesitation at overshoot
    time.sleep(rng.uniform(0.08, 0.18)); t_total += 0.13

    # 5) correct back to exact target
    tx = sx + dx
    while x > tx:
        v = rng.uniform(0.5, 1.4)
        x = max(x - v, tx)
        y += rng.uniform(-0.3, 0.3)
        mv(x, y, buttons=1)

    # 6) settle: 2-3 tiny micro-moves at the target
    for _ in range(rng.randint(2, 3)):
        mv(x + rng.uniform(-0.4, 0.4), y + rng.uniform(-0.3, 0.3), buttons=1)
    time.sleep(rng.uniform(0.18, 0.35)); t_total += 0.25

    # 7) release
    cdp.call("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": round(sx + dx, 1), "y": round(y, 1),
        "button": "left", "buttons": 0, "clickCount": 1}, timeout=15)
    return t_total
