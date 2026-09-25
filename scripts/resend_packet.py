#!/usr/bin/env python3
"""resend_packet.py — resend a worker packet into an EXISTING chat tab.

The cancel-and-resend pattern (operator doctrine 2026-09-25): when a turn
dies mid-work, do NOT burn a new conversation slot — start a new turn in
the SAME chat by re-inserting the packet and submitting. Each turn gets a
fresh sandbox, so a resend is a clean retry of the task.

Usage: resend_packet.py <chat-id-8char> <prompt-file>
"""
import sys, time, json
sys.path.insert(0, '/home/z/replay2/scripts')
import channel
import dispatch_worker as DW

def main():
    cid, prompt_file = sys.argv[1], sys.argv[2]
    prompt = open(prompt_file, encoding='utf-8').read()
    tabs = [t for t in channel.list_tabs() if cid in (t.get('url') or '')]
    if not tabs:
        print(f"no tab for {cid}"); return 1
    c = DW._reconnect(tabs[0]['id'])
    # focus + clear composer, insert chunked, submit via form.requestSubmit
    foc = DW._eval(c, DW.JS_FOCUS_COMPOSER)
    if foc != 'ok':
        print('focus failed:', foc); return 1
    DW._eval(c, DW.JS_CLEAR_COMPOSER)
    time.sleep(0.5)
    CH = 8000
    for off in range(0, len(prompt), CH):
        c.call("Input.insertText", {"text": prompt[off:off+CH]}, timeout=90)
        time.sleep(0.6)
    time.sleep(2)
    ratio = DW._eval(c, f"""(() => {{
      const i = document.querySelector('#chat-input, textarea');
      return i ? String(Math.round(100 * (i.value || '').length / {len(prompt)})) : 'x';
    }})()""")
    print('insert ratio:', ratio)
    if not (97 <= int(ratio) <= 115):
        print('INSERT FAILED'); return 1
    r = DW._eval(c, channel.SUBMIT_JS)
    print('submit:', r)
    time.sleep(6)
    cleared = DW._eval(c, """(() => {
      const i = document.querySelector('#chat-input');
      return i ? String((i.value||'').length) : 'gone';
    })()""")
    print('composer after:', cleared)
    print('url:', DW._eval(c, 'location.href')[:70])
    c.close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
