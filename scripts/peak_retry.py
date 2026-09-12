#!/usr/bin/env python3
"""peak_retry.py — peak-hours gate retry daemon (operator rule: cancel +
retry the previous action).

2026-09-12 forensics: during peak hours the agent gate rejects generations
with a 'Currently in peak hours ... try again later' popup. Observed state
machine on an AFFECTED session:

  message in thread + popup  ==  STAGED-NOT-ACCEPTED (the render shows the
  message in the thread, but the server rejected the generation). Proof:
  clicking Cancel rolls the message back into the composer.

Recovery per round (the operator's prescribed assault):
  1. click Cancel on the popup
  2. wait for the rollback (message re-stages in the composer)
  3. click composer -> Input.insertText(' ') (re-fires React onChange; a
     stale React state is why Enter alone does nothing) -> Enter
  4. if the popup re-arms, sleep CADENCE and repeat

Stops intervening for a session the moment its body grows (generation
running). Pure DOM observation otherwise; never touches the model selector
(never clicks 'Switch to GLM-5.3-Flash').

Usage: peak_retry.py <url_sub>[,<url_sub>...] [--cadence 150]
"""
import json
import sys
import time

sys.path.insert(0, '/home/z/replay2/scripts')
import channel  # noqa: E402

CADENCE = 150


def snapshot(ws):
    return json.loads(ws.eval(r"""
(() => {
  const body = document.body.innerText || '';
  const ta = document.querySelector('#chat-input, textarea');
  return JSON.stringify({
    url: location.href,
    bodyLen: body.length,
    taLen: ta ? (ta.value || '').length : -1,
    popup: [...document.querySelectorAll('button, [role=button]')]
      .some(b => String(b.innerText || '').trim() === 'Switch to GLM-5.3-Flash'),
    cancel: [...document.querySelectorAll('button, [role=button]')]
      .some(b => String(b.innerText || '').trim() === 'Cancel'),
  });
})()
""", timeout=12))


def cancel_popup(ws):
    return ws.eval(r"""
(() => {
  const c = [...document.querySelectorAll('button, [role=button]')]
    .find(b => String(b.innerText || '').trim() === 'Cancel');
  if (!c) return 'none';
  c.click();
  return 'cancelled';
})()
""", timeout=10)


def submit_staged(ws):
    """Re-submit the composer's staged text (click -> insertText space -> Enter)."""
    rect = ws.eval(r"""
(() => {
  const t = document.querySelector('#chat-input, textarea');
  if (!t) return null;
  const r = t.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 40)});
})()
""", timeout=10)
    if rect is None:
        return 'no-composer'
    r = json.loads(rect)
    ws.call('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': r['x'], 'y': r['y'], 'button': 'left', 'clickCount': 1})
    ws.call('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': r['x'], 'y': r['y'], 'button': 'left', 'clickCount': 1})
    time.sleep(0.6)
    ws.call('Input.insertText', {'text': ' '})
    time.sleep(0.9)
    ws.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13})
    ws.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13})
    time.sleep(3)
    return 'submitted'


def log(name, line):
    print(time.strftime('[%H:%M:%S]') + f' [{name}] ' + line, flush=True)


def main():
    subs = sys.argv[1].split(',')
    cadence = CADENCE
    if '--cadence' in sys.argv:
        cadence = int(sys.argv[sys.argv.index('--cadence') + 1])
    log('daemon', f'watching {subs} cadence={cadence}s')
    last_body = {s: None for s in subs}
    rounds = {s: 0 for s in subs}
    while True:
        tabs = channel.list_tabs()
        for sub in subs:
            tab = next((t for t in tabs if sub in (t.get('url') or '')), None)
            if tab is None:
                log(sub, 'TAB LOST (will re-check next cycle)')
                continue
            try:
                ws = channel.CDP(tab['webSocketDebuggerUrl'], timeout=15)
            except Exception as e:
                log(sub, f'CDP-ERR {e!r}'[:90])
                continue
            try:
                st = snapshot(ws)
                if last_body[sub] is not None and st['bodyLen'] > last_body[sub] + 40:
                    log(sub, f"GENERATION RUNNING (body {last_body[sub]}->{st['bodyLen']}) — hands off")
                    rounds[sub] = 0
                elif st['popup']:
                    rounds[sub] += 1
                    log(sub, f"peak popup up (round {rounds[sub]}) — cancel + retry")
                    c = cancel_popup(ws)
                    time.sleep(2.5)
                    st2 = snapshot(ws)
                    if st2['taLen'] > 0:
                        r = submit_staged(ws)
                        st3 = snapshot(ws)
                        log(sub, f"cancel={c} submit={r} -> taLen={st3['taLen']} body={st3['bodyLen']} popup={st3['popup']}")
                    else:
                        log(sub, f"cancel={c} but composer empty (body={st2['bodyLen']}) — message held in thread; observing")
                elif st['taLen'] > 0:
                    # staged without popup — submit directly
                    r = submit_staged(ws)
                    st2 = snapshot(ws)
                    log(sub, f"staged-no-popup submit={r} -> taLen={st2['taLen']} popup={st2['popup']}")
                last_body[sub] = st['bodyLen']
            except Exception as e:
                log(sub, f'ERR {e!r}'[:90])
            finally:
                ws.close()
        time.sleep(cadence)


if __name__ == '__main__':
    main()
