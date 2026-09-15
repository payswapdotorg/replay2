#!/usr/bin/env python3
"""tmp_release_click2.py — exact-row Release click: the matched ancestor must
contain the TARGET title and must NOT contain any EXCLUDE titles."""
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

TARGET = sys.argv[1] if len(sys.argv) > 1 else 'Zeck Developer Doc'
EXCLUDE = [t for t in (sys.argv[2:] if len(sys.argv) > 2 else ['Console'])]

tab = next((t for t in channel.list_tabs() if 'settings/dashboard' in (t.get('url') or '')), None)
if not tab:
    raise SystemExit('no dashboard tab')
c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)

CLICK_JS = r"""
(() => {
  const target = '__TARGET__';
  const exclude = __EXCLUDE__;
  const btns = Array.from(document.querySelectorAll('button'))
    .filter(b => ((b.innerText || '').trim() === 'Release'));
  const report = [];
  for (const b of btns) {
    let el = b.parentElement;
    for (let i = 0; i < 7 && el; i++) {
      const t = el.innerText || '';
      if (t.includes(target)) {
        const hasExclude = exclude.some(x => t.includes(x));
        report.push({depth: i, text: t.slice(0, 120).replace(/\n/g, '|'), hasExclude});
        if (!hasExclude) {  // row-scoped: contains target, no other row titles
          b.click();
          return JSON.stringify({clicked: true, row: t.slice(0, 120).replace(/\n/g, '|'), all: report});
        }
        break;
      }
      el = el.parentElement;
    }
  }
  return JSON.stringify({clicked: false, all: report});
})()
""".replace('__TARGET__', TARGET).replace('__EXCLUDE__', repr(EXCLUDE).replace("'", '"'))

try:
    print(c.eval(CLICK_JS, await_promise=False, timeout=25))
    time.sleep(4)
    state = c.eval(r"""
      (() => {
        const body = document.body.innerText || '';
        const i = body.indexOf('Sandbox');
        return body.slice(i, i + 400);
      })()
    """, await_promise=False, timeout=25)
    print('POST-CLICK SECTION:', state)
finally:
    c.close()
