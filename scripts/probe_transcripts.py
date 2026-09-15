#!/usr/bin/env python3
"""probe_transcripts.py — sample live transcript lengths of worker chat tabs."""
import sys, time
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

targets = {'dep-001': '4e2f61fd', 'dep-010': '5c355d3c', 'dep-020': '003f515c'}
JS_LEN = "document.body.innerText.length"
JS_TAIL = "document.body.innerText.slice(-200).replace(/\\n+/g, ' | ')"

tabs = channel.list_tabs()
for name, cid in targets.items():
    tab = next((t for t in tabs if cid in (t.get('url') or '')), None)
    if not tab:
        print(f'{name}: NO TAB')
        continue
    ws = channel.CDP(tab['webSocketDebuggerUrl'])
    try:
        n = ws.eval(JS_LEN, await_promise=False, timeout=20)
        tail = ws.eval(JS_TAIL, await_promise=False, timeout=20)
        print(f'{name}: len={n} tail={str(tail)[-140:]}')
    except Exception as e:
        print(f'{name}: ERR {str(e)[:120]}')
    finally:
        ws.close()
print('at', time.strftime('%H:%M:%S', time.gmtime()), 'UTC')
