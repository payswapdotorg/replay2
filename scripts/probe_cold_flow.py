#!/usr/bin/env python3
"""probe_cold_flow.py — reproduce the create flow's cold model-menu failure."""
import sys, time, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel
import dispatch_worker as dw

JS_DUMP_MENU = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return JSON.stringify({err: 'no-button'});
  if (b.getAttribute('aria-expanded') !== 'true') b.click();
  const menus = [];
  document.querySelectorAll('[role=menu], [role=listbox]').forEach(m => {
    const leaves = [];
    m.querySelectorAll('*').forEach(e => {
      if (e.children.length === 0) {
        const t = (e.textContent || '').trim();
        if (t && t.length < 70 && !leaves.includes(t)) leaves.push(t);
      }
    });
    menus.push(leaves.slice(0, 20));
  });
  return JSON.stringify({menus: menus, expanded: b.getAttribute('aria-expanded')});
})()"""

def main():
    tab = channel.new_tab('https://chat.z.ai/')
    print('tab:', tab['id'][:8])
    time.sleep(10)
    t2 = next(t for t in channel.list_tabs() if t['id'] == tab['id'])
    c = channel.CDP(t2['webSocketDebuggerUrl'], timeout=30)
    try:
        # step [3/7] equivalent: click Agent nav
        r = c.eval(r"""(() => { const els = [...document.querySelectorAll('a, button, div[role=button]')]; const a = els.find(e => (e.innerText || '').trim() === 'Agent'); if (a) { a.click(); return 'ok'; } return 'no-agent'; })()""", timeout=20)
        print('agent nav:', r)
        time.sleep(2)
        # step [4/7] equivalent: model text
        cur = c.eval(dw.JS_MODEL_TEXT, timeout=15)
        print('model text:', repr(cur))
        # open + dump immediately and after delays
        for delay in (0, 3, 8, 15):
            if delay:
                time.sleep(delay - (0 if delay == 3 else 3 if delay == 8 else 7))
            d = json.loads(c.eval(JS_DUMP_MENU, timeout=20))
            leaves = d.get('menus') or []
            print(f't+{delay}s menu leaves:', leaves[:2] if leaves else 'NO MENU ELEMENT')
            if leaves:
                flat = [x for m in leaves for x in m]
                print('   items:', flat[:12])
        # now the real probe
        res = c.eval(dw.JS_CLICK_MODEL, timeout=20)
        print('JS_CLICK_MODEL:', repr(res))
        cur2 = c.eval(dw.JS_MODEL_TEXT, timeout=15)
        print('model text after click:', repr(cur2))
    finally:
        c.close()

if __name__ == '__main__':
    main()
