#!/usr/bin/env python3
"""vpn_connect.py — one-shot TurboVPN connect via the extension popup.

Lesson-72 procedure: Page.navigate any tab to
chrome-extension://<id>/dist/popup/index.html, DOM-click the power control
(.mt-5.w-16.h-16.cursor-pointer), then verify CONNECTED + egress IP.
Idempotent: if already CONNECTED, just reports.
"""
import json
import re
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

POPUP = "chrome-extension://piplkafkogjfjlofefcobgiccagncean/dist/popup/index.html"
FETCH_JS = ("fetch('https://api.ipify.org',{cache:'no-store'})"
            ".then(r=>r.text()).then(t=>t.trim())")


def main():
    # 0. baseline egress from a normal page tab
    base_ip = None
    for t in channel.list_tabs():
        if t.get("type") == "page" and (t.get("url") or "").startswith("https://chat.z.ai"):
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
            try:
                base_ip = c.eval(FETCH_JS, await_promise=True, timeout=25)
            except Exception as e:
                print("baseline probe err:", e)
            c.close()
            break
    print("baseline egress ip:", base_ip)

    # 1. open a tab and navigate to the popup
    tab = channel.new_tab("about:blank")
    time.sleep(1)
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    c.call("Page.navigate", {"url": POPUP})
    time.sleep(4)

    body = c.eval("document.body.innerText || ''", timeout=20) or ""
    print("popup text (pre):", body[:200].replace("\n", " | "))

    if "CONNECTED" in body.upper():
        print("already CONNECTED")
    else:
        # 2. DOM-click the power control
        clicked = c.eval(
            "(() => { const el = document.querySelector('.mt-5.w-16.h-16.cursor-pointer');"
            " if (!el) return 'NO-EL'; el.click(); return 'CLICKED'; })()",
            timeout=20)
        print("power click:", clicked)
        time.sleep(8)  # connection handshake

    # 3. verify
    body2 = c.eval("document.body.innerText || ''", timeout=20) or ""
    print("popup text (post):", body2[:200].replace("\n", " | "))
    vpn_ip = None
    try:
        vpn_ip = c.eval(FETCH_JS, await_promise=True, timeout=25)
    except Exception as e:
        print("popup egress probe err:", e)
    print("popup-tab egress ip:", vpn_ip)
    print("CONNECTED" in body2.upper() and "vpn state: CONNECTED"
          or "vpn state: NOT-CONFIRMED (check popup text)")

    c.close()
    # close the popup tab (it's a control surface, not a session)
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:9222/json/close/" + tab["id"])
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    result = {"baseline": base_ip, "popup_egress": vpn_ip,
              "popup_connected": "CONNECTED" in body2.upper()}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
