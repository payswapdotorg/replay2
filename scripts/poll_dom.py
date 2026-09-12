#!/usr/bin/env python3
"""poll_dom.py — DOM-based worker progress poller (no reload).

Reads document.body.innerText length and counts occurrences of the
completion-report marker. 1 occurrence = work-order template echo;
>= 2 = the worker's own final report. Also detects streaming markers.
Zero interference: no reload, no clicks — a pure read.
"""
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

CHATS = [
    ("ui-011", "bce1b35e-1b30-4181-9fef-742aec4f7670"),
    ("dep-005", "d71b08bf-d1a5-4468-bf4d-e2bfb6734958"),
]
MARKER = "COMPLETION REPORT"
STAGED = "STAGED:"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, cid in CHATS:
        if only and only not in name:
            continue
        tab = None
        for t in channel.list_tabs():
            if cid in (t.get('url') or ''):
                tab = t
                break
        if not tab:
            print(f"POLL {name}: TAB-LOST")
            continue
        try:
            ws = channel.CDP(tab['webSocketDebuggerUrl'], timeout=20)
            try:
                body = ws.eval(
                    "document.body ? (document.body.innerText || '') : ''",
                    timeout=25) or ''
                n_marker = body.count(MARKER)
                n_staged = body.count(STAGED)
                streaming = any(m in body for m in
                                ('Thinking', 'Generating', 'typing…', 'Ran '))
                tail = [l for l in body.split('\n') if l.strip()][-2:]
                print(f"POLL {name}: chars={len(body)} report={n_marker} "
                      f"staged={n_staged} streaming={streaming} "
                      f"tail={' | '.join(t[:50] for t in tail)[-110:]}")
            finally:
                ws.close()
        except Exception as e:
            print(f"POLL {name}: ERR {type(e).__name__}")


if __name__ == '__main__':
    main()
