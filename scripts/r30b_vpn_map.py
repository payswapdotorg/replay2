#!/usr/bin/env python3
"""r30b_vpn_map.py — map every clickable element in the turbovpn popup."""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = """
(() => {
  const out = [];
  const all = [...document.querySelectorAll('*')];
  for (const e of all) {
    const s = getComputedStyle(e);
    const clickable = s.cursor === 'pointer' || e.tagName === 'BUTTON' ||
                      e.hasAttribute('onclick') || e.getAttribute('role') === 'button';
    if (!clickable) continue;
    const r = e.getBoundingClientRect();
    if (r.width < 5 || r.height < 5) continue;
    out.push({tag: e.tagName, cls: String(e.className).slice(0, 50),
              text: (e.innerText || '').trim().slice(0, 30),
              x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
              w: Math.round(r.width), h: Math.round(r.height)});
  }
  return JSON.stringify(out.slice(0, 20));
})()
"""


def main():
    tabs = [t for t in channel.list_tabs()
            if "piplkafkogjfjlofefcobgiccagncean" in (t.get("url") or "")]
    if not tabs:
        print("no popup tab")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
    try:
        r = c.eval(JS, timeout=12)
        for el in json.loads(r):
            print(el)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
