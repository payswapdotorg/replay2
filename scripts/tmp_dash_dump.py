#!/usr/bin/env python3
"""tmp_dash_dump.py — dump the settings dashboard sandbox section structure."""
import sys, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

tab = next((t for t in channel.list_tabs() if 'settings/dashboard' in (t.get('url') or '')), None)
if not tab:
    raise SystemExit('no dashboard tab')
c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)

JS = r"""
(() => {
  // find the element whose direct text is 'Sandbox'
  const all = Array.from(document.querySelectorAll('*'));
  const head = all.find(e => Array.from(e.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ') === 'Sandbox');
  if (!head) return JSON.stringify({err: 'no Sandbox heading'});
  let root = head;
  for (let i = 0; i < 5 && root.parentElement; i++) root = root.parentElement;
  const txt = (root.innerText || '').slice(0, 1200);
  const btns = Array.from(root.querySelectorAll('button'))
      .map(b => (b.innerText || '').trim().slice(0, 30)).filter(Boolean);
  return JSON.stringify({txt: txt, btns: btns.slice(0, 30)});
})()
"""

print(c.eval(JS, await_promise=False, timeout=25))
c.close()
