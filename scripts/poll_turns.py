#!/usr/bin/env python3
"""poll_turns.py — non-invasive turn-status poller.

Reads the server-side chat tree for the given chat ids via the chat.z.ai
home tab (Bearer token fetch — no reload, no interference with worker
tabs). Reports per chat: assistant message count, content length, and
whether the final-report marker (STAGED:) is present in the last assistant
message. Exit code 0 always; output is a compact one-line-per-chat report.
"""
import json
import sys

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

CHATS = [
    ("rtn-010", "4a5ea97a-4a3c-4f04-8f9f-8b6e3fe355aa"),
    ("rtn-011", "c7087b09-782d-4c73-85a8-3ac69c521260"),
]


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    # Prefer a NON-worker tab for the fetch (home tab) to avoid touching
    # worker tabs at all.
    tab = None
    for t in channel.list_tabs():
        u = t.get('url') or ''
        if 'chat.z.ai' in u and '/c/' not in u:
            tab = t
            break
    if tab is None:
        for t in channel.list_tabs():
            if 'chat.z.ai' in (t.get('url') or ''):
                tab = t
                break
    if tab is None:
        print("POLL: no chat.z.ai tab")
        return
    ws = channel.CDP(tab['webSocketDebuggerUrl'], timeout=25)
    try:
        for name, cid in CHATS:
            if only and only not in name:
                continue
            js = f"""
            (async () => {{
              const t = localStorage.getItem('token') || '';
              const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include',
                headers: {{'Authorization': 'Bearer ' + t}}}});
              const d = await r.json();
              const hist = (d.chat || {{}}).history || {{}};
              const msgs = Object.values(hist.messages || {{}});
              let lastA = null;
              for (const m of msgs) if (m.role === 'assistant') lastA = m;
              if (!lastA) return JSON.stringify({{n: msgs.length, a: 0, len: 0, staged: false, streaming: !!d.chat?.generating}});
              let txt = '';
              const c = lastA.content;
              if (typeof c === 'string') txt = c;
              else if (Array.isArray(c)) for (const p of c) {{
                if (typeof p?.text === 'string') txt += p.text;
              }}
              return JSON.stringify({{n: msgs.length, a: 1, len: txt.length,
                staged: txt.includes('STAGED:') && txt.includes('COMPLETION REPORT'),
                streaming: !!d.chat?.generating}});
            }})()
            """
            try:
                raw = ws.eval(js, await_promise=True, timeout=45)
                d = json.loads(raw)
                print(f"POLL {name}: msgs={d.get('n')} assistant={'yes' if d.get('a') else 'no'} "
                      f"chars={d.get('len')} staged={d.get('staged')} generating={d.get('streaming')}")
            except Exception as e:
                print(f"POLL {name}: ERR {type(e).__name__}")
    finally:
        ws.close()


if __name__ == '__main__':
    main()
