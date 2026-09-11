#!/usr/bin/env python3
"""check_live.py — reload-first status for registry sessions (lesson 19b:
a frozen page does NOT mean a dead turn; ALWAYS Page.reload before reading).

For each live session in the registry: reload the tab, wait, read body text
length + streaming/report markers + tail. Never trusts a stale render.
"""
import json
import os
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

BASE = '/home/z/replay2/scripts'
REG = os.path.join(BASE, 'flags', 'session_registry.jsonl')


def sessions():
    last = {}
    try:
        for line in open(REG):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            name = d.get('name') or '?'
            ev = str(d.get('event') or d.get('stage') or 'created')
            last[name] = dict(d, _ev=ev)
    except Exception:
        pass
    # keep only live-ish
    live = {n: d for n, d in last.items()
            if d['_ev'] not in ('done', 'void', 'closed', 'tab-closed')}
    return live


def tab_by_id(tid):
    try:
        for t in channel.list_tabs():
            if t.get('id') == tid:
                return t
    except Exception:
        pass
    return None


def reload_and_read(tab):
    """Lesson 19b: reload first, then read. Returns dict of state."""
    try:
        c = channel.CDP(tab['webSocketDebuggerUrl'], timeout=20)
        try:
            try:
                c.call('Page.enable', {}, timeout=10)
                c.call('Page.reload', {}, timeout=20)
            except Exception:
                pass  # reload failures fall through to a read attempt
            time.sleep(6)
            body = c.eval("document.body ? (document.body.innerText || '') : ''", timeout=25) or ''
            url = c.eval("location.href", timeout=10) or ''
            streaming = any(m in body for m in ('Thinking', 'Generating', 'typing…', 'Ran '))
            report = ('COMPLETION REPORT' in body)
            tail = [l for l in body.split('\n') if l.strip()][-6:]
            return {'state': 'live', 'chars': len(body), 'url': url,
                    'streaming': streaming, 'report': report,
                    'tail': ' | '.join(t[-4:] for t in tail)[-400:]}
        finally:
            c.close()
    except Exception as e:
        return {'state': f'ERR:{type(e).__name__}', 'chars': 0, 'url': '',
                'streaming': False, 'report': False, 'tail': ''}


def main():
    live = sessions()
    if not live:
        print('no live sessions in registry')
        return 0
    print(f"=== check_live @ {time.strftime('%H:%M:%S')} — {len(live)} session(s)")
    for name, d in live.items():
        print(f"--- {name} (ev={d['_ev']}, tab={str(d.get('tab_id',''))[:12]})")
        tab = tab_by_id(d.get('tab_id', ''))
        if not tab:
            print('    TAB-LOST')
            continue
        st = reload_and_read(tab)
        print(f"    {st['state']}  chars={st['chars']}  streaming={st['streaming']}  "
              f"report={st['report']}  url={st['url'][:60]}")
        if st['tail']:
            print(f"    tail: {st['tail'][:300]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
