#!/usr/bin/env python3
"""check_chat_tail.py — dump the tail of a chat's message tree: last messages,
their status fields, and detect an open/running assistant turn (slot holder).
Usage: check_chat_tail.py <chatId> [N]
"""
import sys, json

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

JS = """
(async () => {
  const t = localStorage.getItem('token') || '';
  const H = { 'Authorization': 'Bearer ' + t };
  const r = await fetch('/api/v1/chats/__CHATID__', { credentials: 'include', headers: H });
  const status = r.status;
  let j = null;
  try { j = await r.json(); } catch (e) {}
  return JSON.stringify({ status: status, body: j });
})()
""".replace('__CHATID__', sys.argv[1])

N = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def main():
    tabs = channel.list_tabs()
    tab = next((t for t in tabs if 'chat.z.ai' in (t.get('url') or '')), None)
    if not tab:
        print("NO chat.z.ai tab open")
        return 1
    c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=60)
    try:
        result = c.eval(JS, await_promise=True, timeout=60000)
        data = result if isinstance(result, (dict, list)) else json.loads(result)
    finally:
        c.close()
    body = data.get('body') or {}
    if data.get('status') != 200:
        print('HTTP', data.get('status'))
        return 1
    msgs = (((body.get('chat') or {}).get('history') or {}).get('messages')) or {}
    if not msgs:
        print('NO MESSAGES')
        return 0
    # leaf = message with no children
    ordered = sorted(msgs.values(), key=lambda m: m.get('timestamp') or 0)
    print('TOTAL MESSAGES:', len(ordered))
    for m in ordered[-N:]:
        role = m.get('role')
        ts = m.get('timestamp')
        kids = m.get('childrenIds') or []
        status = {k: v for k, v in m.items() if 'status' in k.lower() or k in ('done', 'running', 'streaming', 'error', 'pending')}
        content = m.get('content')
        if isinstance(content, list):
            preview = json.dumps(content)[:220]
        else:
            preview = str(content)[:220]
        print(json.dumps({
            'id': (m.get('id') or '')[:8],
            'role': role,
            'ts': ts,
            'children': len(kids),
            'statusFields': status,
            'preview': preview.replace('\n', ' ')[:200],
        }, ensure_ascii=False))
    # running detection
    running = [m.get('id') for m in ordered if str(m.get('status', '')).lower() in ('running', 'streaming', 'pending', 'in_progress')]
    print('RUNNING-STATUS MSGS:', running or 'none')
    return 0


if __name__ == '__main__':
    sys.exit(main())
