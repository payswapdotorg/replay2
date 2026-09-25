#!/usr/bin/env python3
"""r30b_vpn_ui.py — inspect/drive the turbovpn extension popup (file-based).

Usage:
  r30b_vpn_ui.py           — inspect the popup UI (buttons + state)
  r30b_vpn_ui.py connect   — click the connect/start button if present
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

EXT = "chrome-extension://piplkafkogjfjlofefcobgiccagncean/dist/popup/index.html"

JS_INSPECT = """
(() => {
  const t = document.body.innerText || '';
  const btns = [...document.querySelectorAll('button, [role=button], a')];
  const names = btns.map(b => (b.innerText || b.title || '').trim())
                     .filter(x => x && x.length < 40);
  return JSON.stringify({
    title: document.title,
    head: t.trim().split('\\n').slice(0, 12),
    buttons: [...new Set(names)].slice(0, 25),
    connected: /connected|protected/i.test(t),
    disconnected: /disconnected|not protected|unprotected/i.test(t)
  });
})()
"""

JS_CLICK_CONNECT = """
(() => {
  const cands = [...document.querySelectorAll('button, [role=button], a, div[role=switch]')];
  const pick = cands.find(b => {
    const s = ((b.innerText || '') + ' ' + (b.title || '') + ' ' +
               (b.getAttribute('aria-label') || '')).toLowerCase();
    return /^(connect|start|turn on|power|protect|on)$/i.test(s.trim())
        || s.includes('connect') || s.includes('start vpn') || s.includes('turn on');
  });
  if (!pick) return JSON.stringify({clicked: false, reason: 'no-connect-button'});
  pick.click();
  return JSON.stringify({clicked: true, text: (pick.innerText || pick.title || '').slice(0, 40)});
})()
"""


def main():
    act = sys.argv[1] if len(sys.argv) > 1 else "inspect"
    tabs = [t for t in channel.list_tabs()
            if "piplkafkogjfjlofefcobgiccagncean" in (t.get("url") or "")]
    if tabs:
        t = tabs[0]
    else:
        t = channel.new_tab(EXT)
        time.sleep(8)
        live = {x["id"]: x for x in channel.list_tabs()}
        t2 = live.get(t["id"])
        if not t2:
            print("POPUP TAB DIED")
            return 1
        t = t2
    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
    try:
        if act == "connect":
            r = c.eval(JS_CLICK_CONNECT, timeout=12)
            print("CLICK:", r)
            time.sleep(6)
        r2 = c.eval(JS_INSPECT, timeout=12)
        print("STATE:", r2[:600])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
