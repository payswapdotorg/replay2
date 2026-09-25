#!/usr/bin/env python3
"""model_menu_probe.py — passive GLM-5.3 availability probe (Lead diagnostic).

Two-phase read on an EXISTING chat.z.ai tab (creates nothing, sends nothing):
phase 1 opens the model menu; phase 2 (after the popover renders) enumerates
options and closes the menu with Escape. Reports the current model button
text, the full option list, and GLM-5.3 presence.

Usage: python3 scripts/model_menu_probe.py [--watch SECONDS]
  --watch N  re-probe every N seconds (default: single shot)
Exit code: 0 = GLM-5.3 present, 3 = absent, 4 = no usable tab.
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

WANT = "GLM-5.3"

JS_OPEN = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return 'no-button';
  const wasOpen = b.getAttribute('aria-expanded') === 'true';
  if (!wasOpen) { b.click(); }
  return wasOpen ? 'was-open' : 'opened';
})()"""

JS_LIST = r"""(() => {
  const seen = new Set();
  const out = [];
  document.querySelectorAll('[role=menuitem], [role=option], [cmdk-item]').forEach(e => {
    const t = (e.innerText || '').trim().split('\n')[0].trim();
    if (t && !seen.has(t) && t.length < 60) { seen.add(t); out.push(t); }
  });
  return JSON.stringify({models: out});
})()"""

JS_CLOSE = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (b && b.getAttribute('aria-expanded') === 'true') {
    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', bubbles: true}));
    if (b.getAttribute('aria-expanded') === 'true') { b.click(); }
  }
  const b2 = document.querySelector('button.modelSelectorButton');
  return (b2 ? (b2.innerText || '').trim().split('\n')[0] : '?');
})()"""


def probe_once():
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        print("PROBE: no chat.z.ai tab open — cannot probe")
        return 4, None
    tab = tabs[0]
    c = None
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        state = c.eval(JS_OPEN, timeout=15)
        if state == "no-button":
            print("PROBE: model selector button not found")
            return 3, None
        time.sleep(2.5)  # let the popover render
        d = json.loads(c.eval(JS_LIST, timeout=15))
        cur = c.eval(JS_CLOSE, timeout=15)
        models = d.get("models", [])
        present = WANT in models
        print(time.strftime("[%H:%M:%S]"), f"current={cur!r}",
              f"GLM-5.3={'PRESENT' if present else 'ABSENT'}",
              f"menu({len(models)})={models}")
        return (0 if present else 3), d
    except Exception as e:
        print(f"PROBE error: {type(e).__name__}: {e}")
        return 3, None
    finally:
        if c:
            try:
                c.close()
            except Exception:
                pass


def main():
    watch = 0.0
    if "--watch" in sys.argv:
        i = sys.argv.index("--watch")
        watch = float(sys.argv[i + 1] if len(sys.argv) > i + 1 else 60)
    while True:
        rc, _ = probe_once()
        if watch <= 0:
            sys.exit(rc)
        time.sleep(watch)


if __name__ == "__main__":
    main()
