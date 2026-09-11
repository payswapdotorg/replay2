#!/usr/bin/env python3
"""check_chats_list.py — list ALL chat.z.ai conversations via the in-page
chats API (works with no local session registry — fresh-sandbox recovery).

The chats API returns every conversation with ids/titles — use it to map
prior sessions when the session registry is empty (fresh sandbox).
"""
import sys
import json

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

JS = """
(async () => {
  // 2026-09-11 fix: localStorage 'token' is a RAW JWT string now — JSON.parse
  // throws ('Unexpected token e') and every diagnostic silently went blind.
  const t = localStorage.getItem('token') || '';
  const r = await fetch('/api/v1/chats/list?limit=100', {
    credentials: 'include',
    headers: { 'Authorization': 'Bearer ' + t }
  });
  const j = await r.json();
  return JSON.stringify(j);
})()
"""


def main():
    tabs = channel.list_tabs()
    tab = next((t for t in tabs if 'chat.z.ai' in (t.get('url') or '')), None)
    if not tab:
        print("NO chat.z.ai tab open")
        return 1
    c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)
    try:
        result = c.eval(JS, await_promise=True, timeout=30000)
        data = result if isinstance(result, (dict, list)) else json.loads(result)
    finally:
        c.close()

    items = []
    if isinstance(data, dict):
        d = data.get('data', data)
        if isinstance(d, dict):
            items = d.get('items', d.get('list', d.get('records', [])))
        elif isinstance(d, list):
            items = d
    elif isinstance(data, list):
        items = data

    print(f"total chats: {len(items)}")
    for it in items:
        cid = str(it.get('id', it.get('chatId', '?')))
        upd = str(it.get('updatedAt') or it.get('updatedAt') or it.get('createdAt') or '?')
        title = str(it.get('title', '(untitled)'))
        model = str(it.get('model', ''))[:20]
        print(f"{cid[:42]:42} {upd[:19]:19} {model:20} {title[:75]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
