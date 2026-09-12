#!/usr/bin/env python3
"""lead_watch_workers.py — peek both worker sessions + inbox state."""
import sys
sys.path.insert(0, '/home/z/replay2/scripts')
import channel  # noqa: E402


def peek(tabs, url_sub, label, marker):
    tab = next((t for t in tabs if url_sub in (t.get('url') or '')), None)
    if tab is None:
        print("  %s: TAB-LOST" % label)
        return
    try:
        ws = channel.CDP(tab['webSocketDebuggerUrl'], timeout=15)
        try:
            body = ws.eval("String(document.body.innerText || '')", timeout=10)
            busy = ws.eval(
                "(() => { const b = Array.from(document.querySelectorAll('button'))"
                ".map(x => (x.innerText||'').trim());"
                " return b.some(x => /^(Stop|Pause|Halt)$/i.test(x)) ? 'GEN' : 'idle'; })()",
                timeout=8)
            tail = body[-400:]
            popup = 'POPUP' if ('peak hours' in tail or 'personal limit' in tail) else '-'
            mark = 'DONE' if marker and marker in body else '-'
            snippet = body[-90:].replace('\n', ' | ')
            print("  %s: len=%s %s %s %s | %s" % (label, len(body), busy, popup, mark, snippet))
        finally:
            ws.close()
    except Exception as e:
        print("  %s: ERR %r" % (label, e))


def main():
    tabs = channel.list_tabs()
    peek(tabs, '41aff710', 'val014', 'CANDIDATES READY')
    peek(tabs, '994be505', 'val016', '')
    for t in tabs:
        u = t.get('url') or ''
        if 'chat.z.ai' in u and '41aff710' not in u and '994be505' not in u and u != 'https://chat.z.ai/':
            print("  OTHER-TAB: %s" % u[:80])


if __name__ == '__main__':
    main()
