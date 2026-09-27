#!/usr/bin/env python3
"""stage_send.py — drive the composer on a SPECIFIC tab (fresh-tab send).

Same recipe as dispatch_worker.send() but takes an explicit tab id, so a
cleanly-hydrated second tab can be used when the registry tab is saturated.
Usage: stage_send.py <tab-id> <message-file>
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

MSG = open(sys.argv[2]).read() if len(sys.argv) > 2 else sys.stdin.read()
WANT = sys.argv[1]

tab = None
for t in channel.list_tabs():
    if t["id"].startswith(WANT):
        tab = t
        break
if not tab:
    print("tab not found:", WANT)
    sys.exit(2)

c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
try:
    cur = dw._eval(c, "location.href", timeout=15) or ""
    want = sys.argv[3] if len(sys.argv) > 3 else "77db3430"
    if f"/c/{want}" not in cur:
        print("tab not on target chat:", cur[:70])
        sys.exit(3)
    # 1. dismiss promotional dialogs
    for _ in range(2):
        d = dw._eval(c, dw.JS_DISMISS_DIALOG, timeout=10)
        if d == "none":
            break
        print("dismissed dialog:", d)
        time.sleep(1.2)
    # 2. capacity modal check
    try:
        st0 = json.loads(dw._eval(c, dw.JS_CAPACITY_STATE, timeout=15) or "{}")
    except Exception:
        st0 = {}
    if st0.get("capacity") or st0.get("hasCancel"):
        dw._eval(c, dw.JS_CLICK_CANCEL, timeout=15)
        print("cancelled pre-existing capacity modal")
        time.sleep(3)
    # 3. click composer
    comp = dw._eval(c, dw.JS_COMPOSER)
    if not comp:
        print("composer not found")
        sys.exit(2)
    pt = json.loads(comp)
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
    time.sleep(0.5)
    # 4. focus + clear
    focused = dw._eval(c, r"""(() => { const i = document.querySelector('#chat-input, textarea'); return (i && document.activeElement === i) ? 'yes' : 'no'; })()""", timeout=15)
    if focused != "yes":
        dw._eval(c, r"""(() => { const i = document.querySelector('#chat-input, textarea'); if (i) { i.focus(); return 'ok'; } return 'gone'; })()""", timeout=15)
        time.sleep(0.4)
    dw._eval(c, dw.JS_CLEAR_COMPOSER, timeout=15)
    time.sleep(0.3)
    dw._eval(c, r"""(() => { const i = document.querySelector('#chat-input, textarea'); if (i) { i.focus(); return 'ok'; } return 'gone'; })()""", timeout=15)
    time.sleep(0.2)
    # 5. insert
    c.call("Input.insertText", {"text": MSG})
    ok, ratio = dw._wait(c, dw.JS_INSERT_RATIO.replace("__PLEN__", str(len(MSG))), "100", tries=8, sleep=1.0, desc="insert")
    try:
        pct = int(ratio)
    except Exception:
        pct = 0
    print(f"insert ratio: {pct}%")
    if not (97 <= pct <= 115):
        print("INSERT FAILED")
        sys.exit(2)
    # 6. re-click textarea (it grew), verify focus, Enter
    body_before = int(dw._eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
    fp = dw._eval(c, dw.JS_COMPOSER)
    f = json.loads(fp)
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": f["x"], "y": f["y"], "button": "left", "clickCount": 1})
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": f["x"], "y": f["y"], "button": "left", "clickCount": 1})
    time.sleep(0.5)
    focused = dw._eval(c, r"""(() => { const i = document.querySelector('#chat-input, textarea'); return (i && document.activeElement === i) ? 'yes' : 'no'; })()""", timeout=15)
    if focused != "yes":
        dw._eval(c, r"""(() => { const i = document.querySelector('#chat-input, textarea'); if (i) { i.focus(); return 'ok'; } return 'gone'; })()""", timeout=15)
        time.sleep(0.4)
    for typ in ("keyDown", "keyUp"):
        c.call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    time.sleep(6)
    # 7. outcome
    try:
        st = json.loads(dw._eval(c, dw.JS_CAPACITY_STATE, timeout=15) or "{}")
    except Exception:
        st = {}
    cleared = dw._eval(c, r"""(() => { const i = document.querySelector('#chat-input, textarea'); return i ? String((i.value||'').length) : 'gone'; })()""", timeout=20)
    body_now = int(dw._eval(c, "(document.body.innerText||'').length", timeout=15) or 0)
    if st.get("generating"):
        print("SENT: generating")
    elif cleared in ("0", "gone") and body_now > body_before:
        print(f"SENT: composer-cleared+grew ({body_before}->{body_now})")
    elif st.get("capacity") or st.get("hasCancel"):
        print("CAPACITY MODAL UP")
        dw._eval(c, dw.JS_CLICK_CANCEL, timeout=15)
    else:
        print(f"NOT SENT: cleared={cleared} body {body_before}->{body_now}")
finally:
    c.close()
