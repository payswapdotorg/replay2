#!/usr/bin/env python3
"""tl1_status_poll.py — one-shot status snapshot: TL1 sessions + COMP-001
nudge state + sandbox modal presence. Run in a loop by the Lead."""
import sys, json, urllib.request
sys.path.insert(0, '/home/z/replay2/scripts')
import channel, dispatch_worker as dw

TOK = open('/home/z/replay2/scripts/flags/chat_token').read().strip().strip('"')
def call(path, body=None):
    url = f'https://chat.z.ai/api/v1{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    req.add_header('Authorization', f'Bearer {TOK}')
    if data: req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

def chat_state(cid):
    try:
        chat = call(f'/chats/{cid}')
        inner = chat.get('chat') or chat
        msgs = (inner.get('history') or {}).get('messages') or {}
        vals = list(msgs.values()) if isinstance(msgs, dict) else msgs
        ids = [m.get('id') for m in vals if m.get('id')]
        if not ids: return (0, 0, 0)
        batch = call(f'/chats/{cid}/messages/batch', {'ids': ids})
        data = (batch.get('data') or batch.get('messages')) or {}
        items = list(data.values()) if isinstance(data, dict) else data
        nuser = sum(1 for m in items if m.get('role')=='user')
        asst = [m for m in items if m.get('role')=='assistant']
        asst_chars = sum(len(str(m.get('content') or '')) for m in asst)
        last_upd = max((m.get('updated_at') or 0) for m in items) if items else 0
        return (nuser, asst_chars, last_upd)
    except Exception as e:
        return ('ERR', repr(e)[:60], 0)

CHATS = {
    'tl1-a-001': '69cc9c76-08ae-4cb3-9a43-271b52213073',
    'tl1-b-002': 'd0682396-ae2c-4942-b895-582b3b0b7fb2',
    'tl1-c-003': '37b73f72-53dd-47cf-9367-f3f2d85b5f24',
    'comp-nudge': 'e09c6436-e5cf-40a4-b393-b899d4894806',
}
import time
print(f'=== {time.strftime("%H:%M:%S")} UTC ===')
for name, cid in CHATS.items():
    nu, ac, lu = chat_state(cid)
    print(f'{name:12s} user_msgs={nu} asst_chars={ac} last_upd={lu}')
# sandbox modal scan
for t in channel.list_tabs():
    url = t.get('url') or ''
    if 'chat.z.ai' not in url or '/c/' not in url: continue
    try:
        c = channel.CDP(t['webSocketDebuggerUrl'], timeout=15)
        st = json.loads(dw._eval(c, dw.JS_SANDBOX_ROWS, timeout=10) or '{}')
        c.close()
        if st.get('present'):
            print(f'SANDBOX MODAL on tab {t["id"][:8]} ({url.split("/c/")[1][:8]}):')
            for r in st.get('rows') or []:
                print('   row:', r.get('name','?')[:55], '| links:', r.get('links','')[:70])
    except Exception:
        pass
