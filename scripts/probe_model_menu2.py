#!/usr/bin/env python3
"""probe_model_menu2.py — dump ONLY the model dropdown popover items."""
import sys, time, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

JS = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return JSON.stringify({err: 'no-button'});
  if (b.getAttribute('aria-expanded') !== 'true') b.click();
  return 'opened';
})()"""

JS_POPOVER = r"""(() => {
  // find the open popover/menu: the element with role=menu or the dropdown
  // container that appeared near the selector button
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return JSON.stringify({err: 'no-button'});
  const br = b.getBoundingClientRect();
  // candidate containers: role=menu, role=listbox, or fixed-position divs
  let menu = null;
  document.querySelectorAll('[role=menu], [role=listbox]').forEach(m => {
    const r = m.getBoundingClientRect();
    if (r.height > 50) menu = m;
  });
  let items = [];
  const collect = (root) => {
    (root ? root.querySelectorAll('*') : []).forEach(e => {
      if (e.children.length === 0) {
        const t = (e.textContent || '').trim();
        if (t && t.length < 70 && !items.includes(t)) items.push(t);
      }
    });
  };
  if (menu) { collect(menu); return JSON.stringify({menu: 'role-menu', items: items.slice(0, 50)}); }
  // fallback: scan all leaf nodes in fixed/absolute overlays
  document.querySelectorAll('div').forEach(d => {
    const cs = getComputedStyle(d);
    const r = d.getBoundingClientRect();
    if ((cs.position === 'fixed' || cs.position === 'absolute') && r.height > 150 && r.height < 600 && r.width > 150 && r.width < 500 && d.children.length > 0) {
      const txt = (d.innerText || '').slice(0, 40);
      if (txt.includes('GLM') || txt.includes('Model') || txt.includes('model')) {
        collect(d);
      }
    }
  });
  return JSON.stringify({menu: 'overlay-scan', items: items.slice(0, 50)});
})()"""

def main():
    tabs = [t for t in channel.list_tabs() if t['type'] == 'page' and (t.get('url') or '').rstrip('/') == 'https://chat.z.ai']
    tab = tabs[0]
    c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)
    try:
        r = c.eval(JS, timeout=15)
        print('open:', r)
        time.sleep(2.5)
        items = json.loads(c.eval(JS_POPOVER, timeout=20))
        print('menu type:', items.get('menu'))
        print('--- popover items ---')
        for it in items.get('items', []):
            print('  |', repr(it))
    finally:
        c.close()

if __name__ == '__main__':
    main()
