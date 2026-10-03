#!/usr/bin/env python3
"""inspect_modal.py — dump dialog/overlay structure of a chat.z.ai tab."""
import sys
import json

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

JS = r"""
(() => {
  const out = {dialogs: [], overlays: []};
  const norm = (s) => (s || '').slice(0, 120).replace(/\n/g, ' | ');
  for (const dlg of document.querySelectorAll('[role=dialog], [class*=dialog], [class*=Dialog], [class*=modal], [class*=Modal]')) {
    const r = dlg.getBoundingClientRect();
    if (r.width > 10 && r.height > 10) {
      const btns = [...dlg.querySelectorAll('button')].map(b => (b.innerText || '').trim() || (b.getAttribute('aria-label') || 'svg')).slice(0, 6);
      out.dialogs.push({cls: String(dlg.className).slice(0, 60), w: Math.round(r.width), h: Math.round(r.height), txt: norm(dlg.innerText), btns});
    }
  }
  for (const el of document.querySelectorAll('body > div')) {
    const st = getComputedStyle(el);
    if ((st.position === 'fixed' || st.position === 'absolute') && el.offsetWidth > 200 && el.offsetHeight > 100) {
      out.overlays.push({cls: String(el.className).slice(0, 50), w: el.offsetWidth, h: el.offsetHeight, z: st.zIndex, pe: st.pointerEvents, txt: norm(el.innerText)});
    }
  }
  return JSON.stringify(out);
})()
"""


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    tabs = channel.list_tabs()
    t = None
    for x in tabs:
        if (x.get("url") or "").startswith("https://chat.z.ai"):
            if prefix is None or x["id"].startswith(prefix):
                t = x
                break
    if not t:
        raise SystemExit("no tab")
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=25)
    try:
        print(ws.eval(JS, timeout=15)[:2500])
    finally:
        ws.close()


if __name__ == "__main__":
    main()
