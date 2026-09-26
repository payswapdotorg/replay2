#!/usr/bin/env python3
"""lead_followup.py <chat-id> <message-file> — send a Lead follow-up message
into a live worker chat via a FRESH tab (2026-09-26 doctrine).

Why fresh-tab: after a worker turn completes, its dispatch tab's renderer is
often WEDGED (lesson 159) — the composer accepts inserts but Enter and button
clicks go nowhere, and stuck bits-* popovers eat focus. A FRESH tab on the
same /c/<id> URL renders clean, the draft store syncs, and a real
click-focus + Input.insertText + real Enter lands the message (proven on
post003 2026-09-26 01:10Z after 6 failed wedged-tab attempts).

Server-side verification (batch store contains the message tail) is the
commit truth — DOM proofs are advisory only.

Usage: lead_followup.py <chat-id> <message-file>
Exit 0 = verified in batch store.
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402
from batch_probe import call  # noqa: E402


def ev(c, js, timeout=15):
    return c.eval(js, await_promise=False, timeout=timeout)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    cid, msg_file = sys.argv[1], sys.argv[2]
    msg = open(msg_file, encoding="utf-8").read()
    tail = msg[-80:].split()[-1] if msg.split() else "followup"

    t = channel.new_tab(f"https://chat.z.ai/c/{cid}")
    print("fresh tab:", t["id"][:12].upper())
    time.sleep(12)
    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=25)

    # clear any draft first (React-aware), then focus with a real click
    ev(c, r"""(() => {
      const ta = document.querySelector('#chat-input, textarea');
      if (!ta) return 'no-ta';
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, '');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      return 'cleared';
    })()""")
    box = json.loads(ev(c, r"""(() => {
      const ta = document.querySelector('#chat-input, textarea');
      const r = ta.getBoundingClientRect();
      return JSON.stringify({x: r.x + r.width/2, y: r.y + Math.min(r.height/2, 30)});
    })()"""))
    c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": box["x"], "y": box["y"],
                                        "button": "left", "clickCount": 1}, timeout=10)
    c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": box["x"], "y": box["y"],
                                        "button": "left", "clickCount": 1}, timeout=10)
    time.sleep(0.8)
    print("focused:", ev(c, "document.activeElement && document.activeElement.tagName"))

    # insert via the real input pipeline (chunked for safety)
    CH = 4000
    for i in range(0, len(msg), CH):
        c.call("Input.insertText", {"text": msg[i:i + CH]}, timeout=15)
        time.sleep(0.4)
    time.sleep(1.0)
    ta_len = ev(c, "(() => { const ta = document.querySelector('#chat-input, textarea'); return ta ? (ta.value||'').length : -1; })()")
    print("composer len:", ta_len, "expected:", len(msg))
    if str(ta_len) != str(len(msg)):
        print("INSERT INCOMPLETE — aborting (composer will be cleared)")
        ev(c, r"""(() => {
          const ta = document.querySelector('#chat-input, textarea');
          const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, '');
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          return 1;
        })()""")
        c.close()
        return 1

    # real Enter
    c.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter",
                                      "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, timeout=10)
    time.sleep(0.15)
    c.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter",
                                      "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, timeout=10)
    time.sleep(4)
    st = json.loads(ev(c, r"""(() => {
      const ta = document.querySelector('#chat-input, textarea');
      const body = document.body.innerText || '';
      return JSON.stringify({taLen: ta ? (ta.value||'').length : -1, echo: body.length > 0});
    })()"""))
    print("after Enter:", st)
    c.close()

    # server-side verify (batch store)
    for poll in range(8):
        try:
            chat = call(f"/api/v1/chats/{cid}")
            inner = chat.get("chat") or chat
            msgs = (inner.get("history") or {}).get("messages") or {}
            vals = msgs.values() if isinstance(msgs, dict) else msgs
            ids = [m.get("id") for m in vals if m.get("id")]
            batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}, timeout=60)
            data = (batch.get("data") or batch.get("messages")) or {}
            blob = " ".join(json.dumps(m) for m in data.values() if m)
            if tail in blob:
                print(f"SERVER-VERIFIED: follow-up in batch store (poll {poll + 1})")
                return 0
        except Exception as e:
            print("probe err:", type(e).__name__)
        time.sleep(5)
    print("NOT VERIFIED in batch store after 8 polls")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
