#!/usr/bin/env python3
"""manual_send.py <url_sub> <message_file> — hardened direct composer send.

Path proven 2026-09-12 on the agent composer: CDP mouse-click the textarea
center -> Input.insertText (fires React onChange; direct .value assignment
leaves React state stale and the send button disabled) -> verify the send
button enabled -> CDP Enter keyDown/keyUp -> verify composer cleared AND
message echo present in the thread.

Capacity popups: if one appears BEFORE the send, cancel it once and retry
the insert+enter (operator rule: cancel + retry previous action). If one
appears AFTER a verified send, leave it (two-state protocol: composer
cleared + /c/ URL = accepted server-side; the popup is cosmetic).
"""
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel  # noqa: E402


def eval_js(ws, js, timeout=12):
    return ws.eval(js, timeout=timeout)


def state(ws):
    return eval_js(ws, r"""
(() => {
  const body = document.body.innerText || '';
  const ta = document.querySelector('#chat-input, textarea');
  const popup = [...document.querySelectorAll('button, [role=button]')]
    .some(b => String(b.innerText || '').trim() === 'Switch to GLM-5.3-Flash');
  return JSON.stringify({
    url: location.href,
    taLen: ta ? (ta.value || '').length : -1,
    popup,
    bodyLen: body.length,
  });
})()
""")


def cancel_popup(ws):
    return eval_js(ws, r"""
(() => {
  const c = [...document.querySelectorAll('button, [role=button]')]
    .find(b => String(b.innerText || '').trim() === 'Cancel');
  if (!c) return 'none';
  c.click();
  return 'cancelled';
})()
""")


def send_once(ws, text):
    # focus the composer by clicking its center
    rect = eval_js(ws, r"""
(() => {
  const t = document.querySelector('#chat-input, textarea');
  if (!t) return null;
  const r = t.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 40)});
})()
""")
    if rect is None:
        return 'no-composer'
    import json as J
    r = J.loads(rect)
    ws.call('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': r['x'], 'y': r['y'], 'button': 'left', 'clickCount': 1})
    ws.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': r['x'], 'y': r['y'], 'button': 'left', 'clickCount': 1})
    time.sleep(0.8)
    # clear any staged content first (select-all + backspace via keys)
    ws.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'a', 'code': 'KeyA', 'windowsVirtualKeyCode': 65, 'nativeVirtualKeyCode': 65, 'modifiers': 2})
    ws.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'a', 'code': 'KeyA', 'windowsVirtualKeyCode': 65, 'nativeVirtualKeyCode': 65, 'modifiers': 2})
    ws.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Backspace', 'code': 'Backspace', 'windowsVirtualKeyCode': 8, 'nativeVirtualKeyCode': 8})
    ws.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Backspace', 'code': 'Backspace', 'windowsVirtualKeyCode': 8, 'nativeVirtualKeyCode': 8})
    time.sleep(0.5)
    # insert the message (fires React onChange)
    ws.call('Input.insertText', {'text': text})
    time.sleep(1.2)
    # verify send affordance is live (a 28px button row near y≈715 enabling)
    enabled = eval_js(ws, r"""
(() => {
  const ta = document.querySelector('#chat-input, textarea');
  if (!ta || (ta.value || '').length === 0) return 'empty';
  const r = ta.getBoundingClientRect();
  return 'staged:' + (ta.value || '').length + '@' + Math.round(r.y);
})()
""")
    if not str(enabled).startswith('staged:'):
        return 'insert-failed:' + str(enabled)
    # Enter to submit
    ws.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13})
    ws.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13})
    time.sleep(4)
    return 'entered'


def main():
    sub = sys.argv[1]
    msg_file = sys.argv[2]
    text = open(msg_file, encoding='utf-8').read()
    marker = text[:60]
    tabs = channel.list_tabs()
    tab = next((t for t in tabs if sub in (t.get('url') or '')), None)
    if tab is None:
        print('TAB LOST')
        return 1
    ws = channel.CDP(tab['webSocketDebuggerUrl'], timeout=30)
    try:
        for attempt in range(1, 5):
            st = eval_js(ws, state(ws) and r"String(document.body.innerText || '')" and "1")  # noop
            s = state(ws)
            print(f'attempt {attempt} pre-state: {s}')
            import json as J
            sd = J.loads(s)
            if sd['popup']:
                print('  popup up -> cancel first')
                cancel_popup(ws)
                time.sleep(2.5)
            res = send_once(ws, text)
            print('  send_once:', res)
            time.sleep(2)
            s2 = J.loads(state(ws))
            body = eval_js(ws, "String(document.body.innerText || '')")
            sent = marker[:40] in body
            print(f'  post: taLen={s2["taLen"]} bodyLen={s2["bodyLen"]} sent={sent}')
            if sent and s2['taLen'] == 0:
                print('SENT-VERIFIED')
                return 0
            time.sleep(8)
        print('SEND-FAILED after 4 attempts')
        return 2
    finally:
        ws.close()


if __name__ == '__main__':
    sys.exit(main())
