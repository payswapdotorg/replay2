#!/usr/bin/env python3
"""tmp_release_probe.py — inspect (and optionally click) Release buttons for a
target sandbox row on the settings dashboard. Usage: probe|click <title-substr>"""
import sys
import json

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

MODE = sys.argv[1] if len(sys.argv) > 1 else 'probe'
TARGET = sys.argv[2] if len(sys.argv) > 2 else 'Zeck Developer Doc'

tab = next((t for t in channel.list_tabs() if 'settings/dashboard' in (t.get('url') or '')), None)
if not tab:
    raise SystemExit('no dashboard tab')
c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)

PROBE_JS = """
(() => {
  const out = [];
  const els = Array.from(document.querySelectorAll('div,tr,section,li'));
  for (const el of els) {
    const t = (el.innerText || '');
    if (t.includes('__TARGET__') && t.length < 600) {
      const btns = Array.from(el.querySelectorAll('button'));
      out.push({
        text: t.slice(0, 180).replace(/\\n/g, ' | '),
        buttons: btns.map(b => (b.innerText || '').trim()).filter(Boolean),
      });
      if (out.length >= 3) break;
    }
  }
  return JSON.stringify(out);
})()
""".replace('__TARGET__', TARGET)

CLICK_JS = """
(() => {
  const els = Array.from(document.querySelectorAll('div,tr,section,li'));
  for (const el of els) {
    const t = (el.innerText || '');
    if (t.includes('__TARGET__') && t.length < 600) {
      const btn = Array.from(el.querySelectorAll('button'))
        .find(b => ((b.innerText || '').trim().toLowerCase() === 'release'));
      if (btn) { btn.click(); return 'clicked'; }
      return 'no-release-button';
    }
  }
  return 'row-not-found';
})()
""".replace('__TARGET__', TARGET)

try:
    if MODE == 'probe':
        print(c.eval(PROBE_JS, await_promise=False, timeout=25))
    else:
        print(c.eval(CLICK_JS, await_promise=False, timeout=25))
finally:
    c.close()
