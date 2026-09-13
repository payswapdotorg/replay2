#!/usr/bin/env python3
"""check_chat_turns.py — fetch a chat's turns via in-page fetch to inspect
open/running turns (slot holders). Usage: check_chat_turns.py <chatId-or-title-keyword>
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


def summarize_turns(turns):
    out = []
    for t in turns[:20]:
        if isinstance(t, dict):
            out.append({
                'role': t.get('role'),
                'status': t.get('status') or t.get('state'),
                'contentLen': len(json.dumps(t.get('content') or t.get('message') or '')),
                'keys': [k for k in t.keys() if k not in ('content', 'message')][:12],
            })
    return out


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
    status = data.get('status')
    body = data.get('body')
    print('HTTP', status)
    if status != 200 or not body:
        print(json.dumps(data)[:500])
        return 1
    # find turns anywhere in body
    turns = None
    d = body.get('data', body) if isinstance(body, dict) else body
    if isinstance(d, dict):
        turns = d.get('turns') or d.get('messages') or d.get('records')
        if turns is None:
            for k, v in d.items():
                if isinstance(v, list) and v and isinstance(v[0], dict) and 'role' in str(v[0]):
                    turns = v
                    break
    if turns is None:
        print('TOP KEYS:', list(d.keys()) if isinstance(d, dict) else type(d))
        print(json.dumps(body)[:800])
        return 0
    print('TURN COUNT:', len(turns))
    for s in summarize_turns(turns):
        print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
