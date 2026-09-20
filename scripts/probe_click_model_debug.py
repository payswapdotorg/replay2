#!/usr/bin/env python3
"""probe_click_model_debug.py — diagnose why JS_CLICK_MODEL finds no option."""
import sys, time, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel
import dispatch_worker as dw

JS_STRUCT = r"""(() => {
  const b = document.querySelector('button.modelSelectorButton');
  if (!b) return JSON.stringify({err: 'no-button'});
  if (b.getAttribute('aria-expanded') !== 'true') b.click();
  const out = {expanded: b.getAttribute('aria-expanded')};
  // what menus exist
  const menus = [];
  document.querySelectorAll('[role=menu], [role=listbox]').forEach(m => {
    const r = m.getBoundingClientRect();
    menus.push({role: m.getAttribute('role'), cls: (m.className || '').toString().slice(0, 60), h: Math.round(r.height), children: m.children.length});
  });
  out.menus = menus;
  // sample the scanned selector hits
  const sel = '[role=menuitem], [role=option], [cmdk-item], [class*=popover] *, [class*=menu] *, [class*=item] *';
  const hits = document.querySelectorAll(sel).length;
  out.scannedHits = hits;
  // where does 'GLM-5.3' text live? walk up from the leaf
  const leaf = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && (e.textContent || '').trim() === 'GLM-5.3');
  if (leaf) {
    const chain = [];
    let n = leaf;
    for (let i = 0; i < 5 && n; i++) {
      chain.push({tag: n.tagName, role: n.getAttribute('role'), cls: (n.className || '').toString().slice(0, 50)});
      n = n.parentElement;
    }
    out.glm53Chain = chain;
  } else {
    out.glm53Chain = 'LEAF NOT FOUND';
  }
  return JSON.stringify(out);
})()"""

def main():
    tabs = [t for t in channel.list_tabs() if t['type'] == 'page' and (t.get('url') or '').rstrip('/') == 'https://chat.z.ai']
    tab = tabs[0]
    c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)
    try:
        r = c.eval(JS_STRUCT, timeout=20)
        d = json.loads(r)
        print(json.dumps(d, indent=1)[:1200])
        # now run the REAL probe
        time.sleep(1)
        res = c.eval(dw.JS_CLICK_MODEL, timeout=20)
        print('JS_CLICK_MODEL result:', repr(res))
    finally:
        c.close()

if __name__ == '__main__':
    main()
