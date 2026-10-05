#!/usr/bin/env python3
"""diag_model_menu.py — diagnose the GLM-5.3 model-selection failure.

Uses the SAME primitives as dispatch_worker (trusted CDP clicks):
  1. fresh tab -> agents screen
  2. TRUSTED-click the model selector button to open the menu
  3. dump every role=menu container + its BUTTON rows (name/rect)
  4. TRUSTED-click the exact 'GLM-5.3' row (fresh coords each try)
  5. read back selector text + any popup/dialog text
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402
from dispatch_worker import (  # noqa: E402
    JS_AGENT_MODE_ON, JS_AGENT_NAV, JS_MODEL_BTN_POS, JS_MODEL_MENU_OPEN,
    JS_MODEL_OPTION_POS, JS_MODEL_TEXT, _eval, _trusted_click,
)

DUMP_MENUS = r"""(() => {
  const out = [];
  for (const m of document.querySelectorAll('[role=menu]')) {
    const rows = [];
    for (const b of m.querySelectorAll('button')) {
      const t = (b.innerText || '').split('\n')[0].trim();
      if (!t) continue;
      const r = b.getBoundingClientRect();
      rows.push({name: t.slice(0, 32), x: Math.round(r.x), y: Math.round(r.y),
                 w: Math.round(r.width), h: Math.round(r.height)});
    }
    if (rows.length) out.push({menu: (m.id || m.className || '?').toString().slice(0, 30),
                                rows: rows.slice(0, 12)});
  }
  return JSON.stringify(out);
})()"""

DUMP_POPUPS = r"""(() => {
  const out = [];
  document.querySelectorAll('[role=dialog]').forEach(e => {
    const t = (e.innerText || '').trim().split('\n').slice(0, 3).join(' | ');
    if (t) out.push(t.slice(0, 80));
  });
  return JSON.stringify(out.slice(0, 5));
})()"""


def main():
    tab = channel.new_tab("https://chat.z.ai/")
    print("tab", tab["id"][:8], flush=True)
    time.sleep(7)
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        for _ in range(5):
            st = _eval(c, JS_AGENT_MODE_ON)
            if st and "New Task" in st:
                break
            _eval(c, JS_AGENT_NAV, timeout=15)
            time.sleep(2.5)
        print("agent state:", (_eval(c, JS_AGENT_MODE_ON) or "")[:70], flush=True)
        print("model before:", _eval(c, JS_MODEL_TEXT), flush=True)

        # 1) trusted open of the model menu
        if not _trusted_click(c, JS_MODEL_BTN_POS):
            print("TRUSTED MENU OPEN FAILED", flush=True)
        time.sleep(1.8)
        print("menu open?", _eval(c, JS_MODEL_MENU_OPEN), flush=True)
        menus = _eval(c, DUMP_MENUS)
        print("MENUS:", (menus or "NONE")[:2000], flush=True)

        # 2) dump option pos (what dispatch would click)
        pos = _eval(c, JS_MODEL_OPTION_POS)
        print("OPTION POS:", pos, flush=True)

        # 3) trusted click on the option
        clicked = _trusted_click(c, JS_MODEL_OPTION_POS)
        print("option trusted click:", clicked, flush=True)
        time.sleep(1.5)

        # 4) read back
        print("model after:", _eval(c, JS_MODEL_TEXT), flush=True)
        print("menu open after?", _eval(c, JS_MODEL_MENU_OPEN), flush=True)
        print("popups:", _eval(c, DUMP_POPUPS), flush=True)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
