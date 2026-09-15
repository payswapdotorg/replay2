#!/usr/bin/env python3
"""tmp_release_click.py — click the Release button of the sandbox row whose
text contains the target title (row-scoped, not page-scoped)."""
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

TARGET = sys.argv[1] if len(sys.argv) > 1 else 'Zeck Developer Doc'

tab = next((t for t in channel.list_tabs() if 'settings/dashboard' in (t.get('url') or '')), None)
if not tab:
    raise SystemExit('no dashboard tab')
c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)

CLICK_JS = r"""
(() => {
  const btns = Array.from(document.querySelectorAll('button'))
    .filter(b => ((b.innerText || '').trim() === 'Release'));
  for (const b of btns) {
    let el = b.parentElement;
    for (let i = 0; i < 6 && el; i++) {
      const t = el.innerText || '';
      if (t.includes('__TARGET__') && t.length < 300) {
        b.click();
        return 'clicked-row: ' + t.slice(0, 80).replace(/\n/g, ' | ');
      }
      el = el.parentElement;
    }
  }
  return 'no-row-matched';
})()
""".replace('__TARGET__', TARGET)

try:
    print(c.eval(CLICK_JS, await_promise=False, timeout=25))
    time.sleep(4)
    # verify post-click state
    state = c.eval(r"""
      (() => {
        const body = document.body.innerText || '';
        const i = body.indexOf('Sandbox');
        return body.slice(i, i + 500);
      })()
    """, await_promise=False, timeout=25)
    print('POST-CLICK SECTION:', state)
finally:
    c.close()
