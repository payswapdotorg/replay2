#!/usr/bin/env python3
"""recover_capacity.py <url-uuid> — wait out GLM-5.3 capacity, then recover the send.

For a session whose prompt sits in the transcript + composer draft but whose
generation is blocked by the 'Model is currently at capacity' dialog: polls
once a minute WITHOUT clicking Cancel (cancel destroys new-task sessions);
when capacity clears it dismisses the dialog and re-sends from the draft.
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel

UUID = sys.argv[1]
FLAG = os.path.join(BASE, "flags/capacity_recover.json")
PIDFILE = os.path.join(BASE, "flags/capacity_recover.pid")


def _clear_flag():
    for p in (FLAG, PIDFILE):
        try:
            os.remove(p)
        except Exception:
            pass


def find_tab():
    for t in channel.list_tabs():
        if UUID in (t.get("url") or ""):
            return t
    return None


def main():
    for attempt in range(240):  # up to 4 hours
        tab = find_tab()
        if not tab:
            print(f"[{attempt}] tab LOST — session died", flush=True)
            _clear_flag()
            return 2
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
            st = json.loads(c.eval(r"""(() => {
              const body = document.body.innerText || '';
              const i = document.querySelector('#chat-input, textarea');
              const btns = Array.from(document.querySelectorAll('button')).map(b => (b.innerText||'').trim());
              return JSON.stringify({capacity: body.includes('currently at capacity'),
                                     composer: i ? (i.value||'').length : -1,
                                     chars: body.length,
                                     generating: btns.some(b => /^(Stop|Pause|Halt)$/i.test(b))});
            })()""", timeout=20) or "{}")
            c.close()
        except Exception as e:
            print(f"[{attempt}] busy {type(e).__name__}", flush=True)
            time.sleep(60)
            continue
        if st.get("generating"):
            print(f"[{attempt}] GENERATING (chars={st.get('chars')}) — recovered", flush=True)
            _clear_flag()
            return 0
        if not st.get("capacity"):
            print(f"[{attempt}] capacity cleared chars={st.get('chars')}", flush=True)
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
            try:
                c.call("Page.bringToFront", {}, timeout=10)
                time.sleep(1)
                c.eval(r"""(() => {
                  const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').trim() === 'Cancel');
                  if (b) b.click();
                  return 'ok';
                })()""", timeout=15)
                time.sleep(4)
                body = c.eval("document.body.innerText || ''", timeout=20) or ""
                if "currently at capacity" in body:
                    print(f"[{attempt}] capacity returned", flush=True)
                    c.close()
                    time.sleep(60)
                    continue
                comp = c.eval("(() => { const i = document.querySelector('#chat-input, textarea'); return i ? String((i.value||'').length) : 'gone'; })()", timeout=15)
                if comp not in ("0", "gone") and int(comp) > 1000:
                    # re-send the retained draft
                    alt = c.eval(r"""(() => {
                      const i = document.querySelector('#chat-input, textarea');
                      const form = i ? i.closest('form') : null;
                      if (!form) return '';
                      const btns = Array.from(form.querySelectorAll('button'))
                        .filter(b => !b.disabled && b.getBoundingClientRect().width > 0);
                      const b = btns[btns.length - 1];
                      const r = b.getBoundingClientRect();
                      return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
                    })()""", timeout=15)
                    if alt:
                        pt = json.loads(alt)
                        c.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
                        c.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1})
                        time.sleep(6)
                time.sleep(10)
                body = c.eval("document.body.innerText || ''", timeout=20) or ""
                gen = c.eval(r"""(() => {
                  const btns = Array.from(document.querySelectorAll('button')).map(b => (b.innerText||'').trim());
                  return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 'yes' : 'no';
                })()""", timeout=15)
                print(f"[{attempt}] after recovery: generating={gen} capacity={'currently at capacity' in body}", flush=True)
                if gen == "yes" or "currently at capacity" not in body:
                    c.close()
                    _clear_flag()
                    return 0
            finally:
                c.close()
            time.sleep(60)
            continue
        if attempt % 10 == 0:
            print(f"[{attempt}] still capacity-blocked (chars={st.get('chars')})", flush=True)
        time.sleep(60)
    return 3


if __name__ == "__main__":
    try:
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    try:
        rc = main()
    except Exception as e:
        import traceback
        with open(os.path.join(BASE, "logs/recover.log"), "a") as f:
            f.write(f"FATAL: {e!r}\n{traceback.format_exc()}\n")
        rc = 99
    sys.exit(rc)
