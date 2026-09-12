#!/usr/bin/env python3
"""composer_dump.py <url_sub> — dump composer-area buttons + placeholder."""
import json
import sys

sys.path.insert(0, '/home/z/replay2/scripts')
import channel  # noqa: E402

JS = r"""
(() => {
  const out = [];
  for (const b of document.querySelectorAll('button, [role=button]')) {
    const r = b.getBoundingClientRect();
    if (r.width < 18 || r.height < 18) continue;
    if (r.y < 480) continue;
    const aria = (b.getAttribute('aria-label') || '');
    const txt = (b.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 22);
    out.push({aria: aria.slice(0, 30), txt, x: Math.round(r.x + r.width / 2),
              y: Math.round(r.y + r.height / 2), dis: b.disabled});
  }
  const ta = document.querySelector('#chat-input');
  return JSON.stringify({btns: out.slice(0, 14),
                         placeholder: ta ? ta.placeholder : 'n/a',
                         taLen: ta ? (ta.value || '').length : -1});
})()
"""


def main():
    sub = sys.argv[1]
    tabs = channel.list_tabs()
    tab = next((t for t in tabs if sub in (t.get('url') or '')), None)
    if tab is None:
        print('TAB LOST')
        return 1
    ws = channel.CDP(tab['webSocketDebuggerUrl'], timeout=20)
    try:
        d = json.loads(ws.eval(JS, timeout=12))
        print('placeholder:', repr(d['placeholder']))
        print('composer-len:', d['taLen'])
        for b in d['btns']:
            print(b)
    finally:
        ws.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
