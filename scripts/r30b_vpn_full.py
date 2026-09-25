#!/usr/bin/env python3
"""r30b_vpn_full.py — full text dump of the turbovpn popup."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = """
(() => {
  const t = document.body.innerText || '';
  const dlg = document.querySelector('[role=dialog], [class*=modal]');
  return JSON.stringify({
    full: t.slice(0, 1200),
    dialog: dlg ? (dlg.innerText || '').slice(0, 400) : null,
    html_len: document.documentElement.outerHTML.length
  });
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
        d = json.loads(r)
        print("FULL TEXT:")
        print(d["full"])
        print("\nDIALOG:", d["dialog"])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
