#!/usr/bin/env python3
"""probe_model_menu.py — dump the agents-tab model selector state + menu items."""
import sys, time, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

JS_CURRENT = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  return b ? ((b.innerText || '').trim().split('\n')[0] || '?') : 'no-button';
})()"""

JS_MENU = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return 'no-button';
  if (b.getAttribute('aria-expanded') !== 'true') b.click();
  return 'opened';
})()"""

JS_ITEMS = r"""(() => {
  const out = [];
  document.querySelectorAll('[role=menuitem], [role=option], li, div, button').forEach(e => {
    const r = e.getBoundingClientRect();
    const t = (e.innerText || '').trim();
    if (r.width > 100 && r.height > 20 && r.height < 140 && t && t.length < 90 && !out.includes(t)) out.push(t);
  });
  return JSON.stringify(out.slice(0, 40));
})()"""

def main():
    tabs = [t for t in channel.list_tabs() if t['type'] == 'page' and (t.get('url') or '').rstrip('/') == 'https://chat.z.ai']
    if not tabs:
        print('NO HOME TAB — opening one')
        tab = channel.new_tab('https://chat.z.ai/')
        time.sleep(12)
        tabs = [t for t in channel.list_tabs() if t['id'] == tab['id']]
        # click Agent nav first
        c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)
        c.eval(r"""(() => { const els = [...document.querySelectorAll('a, button, div[role=button]')]; const a = els.find(e => (e.innerText || '').trim() === 'Agent'); if (a) a.click(); return 'ok'; })()""", timeout=20)
        time.sleep(5)
        c.close()
    tab = tabs[0]
    c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)
    try:
        cur = c.eval(JS_CURRENT, timeout=15)
        print('current model shown:', repr(cur))
        if cur == 'no-button':
            # maybe need Agent view active; click Agent nav
            c.eval(r"""(() => { const els = [...document.querySelectorAll('a, button, div[role=button]')]; const a = els.find(e => (e.innerText || '').trim() === 'Agent'); if (a) a.click(); return 'ok'; })()""", timeout=20)
            time.sleep(4)
            cur = c.eval(JS_CURRENT, timeout=15)
            print('current model after Agent-click:', repr(cur))
        m = c.eval(JS_MENU, timeout=15)
        print('menu:', m)
        time.sleep(2.5)
        items = c.eval(JS_ITEMS, timeout=20)
        print('--- menu items ---')
        for it in json.loads(items):
            print('  |', repr(it))
    finally:
        c.close()

if __name__ == '__main__':
    main()
