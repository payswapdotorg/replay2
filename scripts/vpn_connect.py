#!/usr/bin/env python3
"""vpn_connect.py — TurboVPN tunnel control via CDP (lead station tooling).

Rebuilt 2026-09-30 after sandbox reset #12 wiped the unpushed copy.
Protocol (AGENT_BOOT_PROMPT lesson 45/49 + field practice):
  1. open the TurboVPN popup page (chrome-extension://piplkafkogjfjlofefcobgiccagncean/dist/popup/index.html)
  2. click the main connect control (rendered Vue DOM)
  3. verify tunnel health: browser egress IP != shell direct IP
Usage:
  python3 vpn_connect.py status   # report connect-status + egress split
  python3 vpn_connect.py connect  # ensure tunnel is up (click if needed)
  python3 vpn_connect.py toggle   # lesson-72: off->on toggle heal
"""
import json
import subprocess
import sys
import time
import urllib.request

import websocket  # websocket-client, /home/z/.venv

CDP = "http://127.0.0.1:9222"
EXT_ID = "piplkafkogjfjlofefcobgiccagncean"
POPUP = f"chrome-extension://{EXT_ID}/dist/popup/index.html"
IP_ECHO = "https://api.ipify.org/?format=json"


def http_json(path, method="GET"):
    req = urllib.request.Request(CDP + path, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def new_tab(url):
    try:
        return http_json(f"/json/new?{url}", method="PUT")
    except Exception:
        return http_json(f"/json/new?{url}", method="POST")


def close_tab(tid):
    try:
        urllib.request.urlopen(f"{CDP}/json/close/{tid}", timeout=10).read()
    except Exception:
        pass


def ws_eval(ws, expr, await_promise=False):
    ws.send(json.dumps({
        "id": int(time.time() * 1000) % 100000,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True,
                   "awaitPromise": await_promise},
    }))
    while True:
        m = json.loads(ws.recv())
        if m.get("id"):
            return m.get("result", {}).get("result", {})


def open_popup():
    t = new_tab(POPUP)
    time.sleep(6)  # Vue app boot (4s raced first render on a cold profile)
    return t


def popup_state(ws):
    """2026-09-30 field probe: the popup is a Vue app; the main control is a
    64x64 div (classes w-16 h-16 cursor-pointer) BELOW the 'Tap to Connect'
    text; status is read from body.innerText (CONNECTED + timer)."""
    r = ws_eval(ws, """
        (() => {
          const text = document.body.innerText || '';
          const ctl = document.querySelector('div[class*="w-16"][class*="h-16"][class*="cursor-pointer"]');
          return JSON.stringify({
            text: text.replace(/\n/g, ' | ').slice(0, 160),
            ctl: ctl ? {x: ctl.getBoundingClientRect().x, y: ctl.getBoundingClientRect().y} : null,
          });
        })()
    """)
    try:
        return json.loads(r.get("value", "{}"))
    except Exception:
        return {"raw": r}


def browser_ip(ws):
    r = ws_eval(ws, f"fetch('{IP_ECHO}').then(r=>r.text())", await_promise=True)
    return (r.get("value") or "").strip()


def shell_ip():
    try:
        return urllib.request.urlopen(IP_ECHO, timeout=15).read().decode().strip()
    except Exception as e:
        return f"ERR:{e}"


def click_connect(ws, state):
    # the 64x64 main control div (field-proven 2026-09-30)
    r = ws_eval(ws, """
        (() => {
          const el = document.querySelector('div[class*="w-16"][class*="h-16"][class*="cursor-pointer"]');
          if (!el) return 'NOT FOUND';
          const rect = el.getBoundingClientRect();
          el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true,
            clientX: rect.x + 32, clientY: rect.y + 32}));
          return 'CLICKED 64x64 control at ' + Math.round(rect.x) + ',' + Math.round(rect.y);
        })()
    """)
    return r.get("value", "?")


def status_string(state):
    t = (state.get("text") or "").lower()
    if "connected" in t and "disconnected" not in t:
        return "connected"
    if "connecting" in t:
        return "connecting"
    if "tap to connect" in t or "connect" in t:
        return "disconnected"
    return "unknown"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    t = open_popup()
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30)
    try:
        state = popup_state(ws)
        st = status_string(state)
        print(f"[vpn] popup state: {st}  ({state.get('text', '')[:100]})")

        if mode in ("connect", "toggle"):
            if st == "connected" and mode == "connect":
                print("[vpn] already connected — no click")
            else:
                msg = click_connect(ws, state)
                print(f"[vpn] {msg}")
                for i in range(12):  # up to 60s tunnel establishment
                    time.sleep(5)
                    state = popup_state(ws)
                    st = status_string(state)
                    print(f"[vpn]   {5 * (i + 1)}s: {st}")
                    if st == "connected":
                        break

        bip = browser_ip(ws)
        sip = shell_ip()
        bip_ip = (bip or "").split('"')[-2] if '"ip"' in (bip or "") else bip
        sip_ip = (sip or "").split('"')[-2] if '"ip"' in (sip or "") else sip
        healthy = bip_ip and sip_ip and bip_ip != sip_ip
        print(f"[vpn] browser egress: {bip_ip}")
        print(f"[vpn] shell  direct: {sip_ip}")
        print(f"[vpn] TUNNEL {'HEALTHY (egress split verified)' if healthy else 'UNHEALTHY (no split)'}")
        return 0 if healthy or mode == "status" else 1
    finally:
        ws.close()
        close_tab(t["id"])


if __name__ == "__main__":
    sys.exit(main())
