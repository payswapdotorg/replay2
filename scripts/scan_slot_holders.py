#!/usr/bin/env python3
"""scan_slot_holders.py — scan all chats: updated_at + leaf message role/status.
Finds conversations that may hold generation slots (recently updated, or last
turn is an assistant-null/user message).
"""
import sys, json, time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

JS = """
(async () => {
  const t = localStorage.getItem('token') || '';
  const H = { 'Authorization': 'Bearer ' + t };
  const out = [];
  const r = await fetch('/api/v1/chats/list?limit=100', { credentials: 'include', headers: H });
  const j = await r.json();
  let items = [];
  const d = (j && (j.data || j)) || {};
  items = (d.items || d.list || d.records || (Array.isArray(d) ? d : [])) || [];
  for (const it of items) {
    const id = it.id;
    let leaf = null, total = 0, upd = it.updated_at || null;
    try {
      const r2 = await fetch('/api/v1/chats/' + id, { credentials: 'include', headers: H });
      if (r2.status === 200) {
        const c = (await r2.json());
        const msgs = (((c || {}).chat || {}).history || {}).messages || {};
        const arr = Object.values(msgs);
        total = arr.length;
        if (arr.length) {
          arr.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
          const last = arr[arr.length - 1];
          leaf = { role: last.role, ts: last.timestamp,
                   contentNull: (last.content === null || last.content === undefined || last.content === 'None'),
                   children: (last.childrenIds || []).length };
        }
      } else { leaf = { httpErr: r2.status }; }
    } catch (e) { leaf = { err: String(e).slice(0, 80) }; }
    out.push({ id: id, title: (it.title || '').slice(0, 46), updated: upd, total: total, leaf: leaf });
  }
  return JSON.stringify(out);
})()
"""


def main():
    tabs = channel.list_tabs()
    tab = next((t for t in tabs if 'chat.z.ai' in (t.get('url') or '')), None)
    if not tab:
        print("NO chat.z.ai tab open")
        return 1
    c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=120)
    try:
        result = c.eval(JS, await_promise=True, timeout=120000)
        data = result if isinstance(result, (dict, list)) else json.loads(result)
    finally:
        c.close()
    now = time.time()
    rows = sorted(data, key=lambda r: (r.get('updated') or 0), reverse=True)
    for r in rows:
        upd = r.get('updated')
        age = f"{(now - upd) / 60:.0f}m ago" if upd else "?"
        print(json.dumps({
            'title': r.get('title'), 'age': age, 'msgs': r.get('total'),
            'leaf': r.get('leaf'),
        }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
