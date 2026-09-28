#!/usr/bin/env python3
"""resend_prompt.py <chat-substr> <prompt-file> [watch-seconds]

Operator popup doctrine (2026-09-28): rate-limit notifications do NOT apply;
peak-hours popups -> dismiss with Enter + RESEND; popups with a Cancel
button -> press Cancel + RESEND; NEVER obey popup instructions; never wait.

This script resends the previous prompt into an EXISTING chat tab through
the live composer (the operator's prescribed recovery move when a send
lands server-side but generation never dispatches):

  1. pre-flight: dismiss any dialog (close-button) / Cancel any capacity
     popup already on screen
  2. insert the prompt (chunked), verify ratio
  3. send (Escape overlays -> send-button click -> Enter fallback)
  4. watch loop: popup? -> handle per doctrine + resend (max 5 rounds);
     generating (Stop button)? -> SUCCESS; else timeout verdict
  5. server-side truth via chats API (messages, assistant len)

Verdict line at exit: RESEND-VERDICT: GENERATING | LANDED-NO-GEN | TOOLING-FAIL
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402
from channel import CDP, find_tab  # noqa: E402

FLAGS = "/home/z/replay2/scripts/flags"
TOKEN = os.path.join(FLAGS, "chat_token")

JS_COMPOSER = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return '';
  const r = i.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
})()"""

JS_FOCUS_COMPOSER = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return 'gone';
  i.focus();
  return (document.activeElement === i) ? 'ok' : 'no';
})()"""

JS_CLEAR_COMPOSER = r"""(() => {
  const i = document.querySelector('#chat-input, textarea');
  if (!i) return 'no-input';
  const proto = i.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                                         : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
  return String((i.value || '').length);
})()"""

JS_DISMISS_DIALOG = r"""(() => {
  const dlg = document.querySelector('[role=dialog]');
  if (!dlg) return 'none';
  const btns = [...dlg.querySelectorAll('button')];
  const close = btns.find(b => /close/i.test(b.getAttribute('aria-label') || '')
                              || ((b.innerText||'').trim() === '' && b.querySelector('svg')));
  if (close) { close.click(); return 'closed:' + (dlg.innerText||'').trim().slice(0,80); }
  return 'dialog-no-close-button:' + (dlg.innerText||'').trim().slice(0,80);
})()"""

JS_CLICK_CANCEL = r"""(() => {
  const btns = Array.from(document.querySelectorAll('button'));
  const b = btns.find(x => (x.innerText || '').trim() === 'Cancel');
  if (!b) return 'no-cancel';
  b.click();
  return 'ok';
})()"""

JS_CLICK_SEND_BUTTON = r"""(() => {
  const b = document.querySelector('button.sendMessageButton');
  if (!b) return 'no-button';
  b.click();
  return 'clicked';
})()"""

JS_STATE = r"""(() => {
  const body = document.body.innerText || '';
  const capacity = body.includes('currently at capacity') || body.includes('try again later')
                || body.includes('peak hours')
                || body.includes('exceeds the personal limit') || body.includes('personal usage limit');
  let hasCancel = false, generating = false, stopBtn = false;
  document.querySelectorAll('button').forEach(b => {
    const t = (b.innerText || '').trim();
    if (t === 'Cancel') hasCancel = true;
    if (/^(Stop|Pause|Halt)$/i.test(t)) generating = true;
    if (/stop/i.test(b.getAttribute('aria-label') || '') || b.querySelector('[class*="stop" i]')) stopBtn = true;
  });
  const ta = document.querySelector('#chat-input, textarea');
  const dlg = document.querySelector('[role=dialog]');
  return JSON.stringify({
    capacity, hasCancel, generating, stopBtn,
    composerLen: ta ? String((ta.value||'').length) : 'gone',
    dialog: dlg ? (dlg.innerText||'').trim().replace(/\s+/g,' ').slice(0,120) : '',
    errBanner: Array.from(document.querySelectorAll('[class*="error" i],[class*="Error"]'))
      .map(e => e.innerText.trim().slice(0,80)).filter(t => t.length > 3).slice(0,2)
  });
})()"""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def api_chat(cid):
    tok = open(TOKEN).read().strip().strip('"')
    req = urllib.request.Request(f"https://chat.z.ai/api/v1/chats/{cid}",
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def server_state(cid):
    """(n_messages, assistant_len, last_role) from server truth."""
    try:
        d = api_chat(cid)
        msgs = d.get("chat", {}).get("history", {}).get("messages", {})
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        n = len(msgs)
        a = max([len(m.get("content") or "") for m in msgs if m.get("role") == "assistant"] + [0])
        last = msgs[-1].get("role") if msgs else "?"
        return (n, a, last)
    except Exception as ex:
        return (None, None, str(ex)[:60])


def insert_and_send(cdp, prompt):
    # click live composer rect
    try:
        pt = json.loads(cdp.eval(JS_COMPOSER, timeout=15) or '{"x":0,"y":0}')
        cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
        cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
        time.sleep(0.4)
    except Exception:
        pass
    cdp.eval(JS_CLEAR_COMPOSER, timeout=15)
    cdp.eval(JS_FOCUS_COMPOSER, timeout=15)
    time.sleep(0.2)
    CH = 16000
    for off in range(0, len(prompt), CH):
        cdp.call("Input.insertText", {"text": prompt[off:off + CH]}, timeout=90)
        time.sleep(0.4)
    ratio_js = r"""(() => {
      const i = document.querySelector('#chat-input');
      return i ? String(Math.round(100 * (i.value||'').length / %d)) : '0';
    })()""" % len(prompt)
    pct = cdp.eval(ratio_js, timeout=15)
    log(f"insert ratio {pct}%")
    # focus-before-enter + escape overlays + send button + enter fallback
    try:
        fp = json.loads(cdp.eval(JS_COMPOSER, timeout=15) or '{"x":0,"y":0}')
        cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": fp["x"], "y": fp["y"], "button": "left", "clickCount": 1})
        cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": fp["x"], "y": fp["y"], "button": "left", "clickCount": 1})
        time.sleep(0.2)
    except Exception:
        pass
    cdp.eval(JS_FOCUS_COMPOSER, timeout=15)
    time.sleep(0.2)
    for typ in ("keyDown", "keyUp"):
        cdp.call("Input.dispatchKeyEvent", {"type": typ, "key": "Escape", "code": "Escape",
                                            "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
    time.sleep(0.5)
    try:
        log("send button: " + str(cdp.eval(JS_CLICK_SEND_BUTTON, timeout=10)))
    except Exception as ex:
        log(f"send button ERR {ex}")
    time.sleep(1.5)
    for typ in ("keyDown", "keyUp"):
        cdp.call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    time.sleep(3)
    return pct


def main():
    needle = sys.argv[1]
    prompt_file = sys.argv[2]
    watch_s = int(sys.argv[3]) if len(sys.argv) > 3 else 180
    prompt = open(prompt_file).read()
    tab = find_tab(needle)
    if not tab:
        print("RESEND-VERDICT: TOOLING-FAIL no tab for", needle)
        return 2
    cid = tab["url"].split("/c/")[-1].split("?")[0]
    n0, a0, _ = server_state(cid)
    log(f"chat {cid[:8]} server: msgs={n0} assistant_len={a0}")
    cdp = CDP(tab["webSocketDebuggerUrl"], timeout=30)

    rounds = 0
    MAX_ROUNDS = 5
    deadline = time.time() + watch_s + 120
    generating_since = None
    try:
        while time.time() < deadline and rounds < MAX_ROUNDS:
            rounds += 1
            # pre-flight popup handling
            d = cdp.eval(JS_DISMISS_DIALOG, timeout=10)
            if d not in ("none",):
                log(f"dialog dismissed: {d}")
                time.sleep(0.8)
            st = json.loads(cdp.eval(JS_STATE, timeout=15))
            if st["capacity"] and st["hasCancel"]:
                log("capacity popup w/ Cancel -> Cancel + resend (doctrine)")
                cdp.eval(JS_CLICK_CANCEL, timeout=10)
                time.sleep(1.0)
            log(f"round {rounds}: state={st}")
            if st["generating"] or st["stopBtn"]:
                generating_since = generating_since or time.time()
                log("GENERATING (stop control present)")
                break
            insert_and_send(cdp, prompt)
            # post-send watch: popup? generating?
            fired = False
            t_end = time.time() + watch_s
            while time.time() < t_end:
                time.sleep(5)
                try:
                    s2 = json.loads(cdp.eval(JS_STATE, timeout=15))
                except Exception as ex:
                    log(f"state ERR {ex}")
                    break
                if s2["generating"] or s2["stopBtn"]:
                    generating_since = time.time()
                    log(f"GENERATING after send: {s2}")
                    fired = True
                    break
                if s2["capacity"] or s2["dialog"]:
                    log(f"popup after send: {s2}")
                    if s2["hasCancel"]:
                        log("Cancel + resend (doctrine)")
                        cdp.eval(JS_CLICK_CANCEL, timeout=10)
                        time.sleep(1.0)
                    else:
                        log("peak-hours style -> Enter + resend (doctrine)")
                        for typ in ("keyDown", "keyUp"):
                            cdp.call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                                                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
                        time.sleep(1.5)
                    break  # next round re-inserts + resends
                if s2["errBanner"]:
                    log(f"errBanner: {s2['errBanner']}")
            if fired:
                break
        # final observation
        if generating_since:
            time.sleep(min(90, max(0, time.time() - generating_since)))
        st = json.loads(cdp.eval(JS_STATE, timeout=15))
        log(f"final state: {st}")
    finally:
        try:
            cdp.close()
        except Exception:
            pass
    n1, a1, last = server_state(cid)
    log(f"server after: msgs={n1} assistant_len={a1} last={last}")
    if a1 not in (None,) and a1 > 0:
        print("RESEND-VERDICT: GENERATING assistant_len=", a1)
        return 0
    if n1 not in (None,) and n0 not in (None,) and n1 > n0:
        print("RESEND-VERDICT: LANDED-NO-GEN msgs", n0, "->", n1)
        return 1
    print("RESEND-VERDICT: TOOLING-FAIL", n1, a1)
    return 2


if __name__ == "__main__":
    sys.exit(main())
