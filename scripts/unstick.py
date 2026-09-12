#!/usr/bin/env python3
"""unstick.py — the operator's manual-healing protocol, automated (2026-09-12).

OPERATOR DIRECTIVES (2026-09-12, binding):
- NEVER wait out a popup or any 'try again later' / 'usage exceeds' /
  'peak hours' message. Dismiss and retry immediately.
- Peak-hours popups: dismiss (Enter) + resend.
- Popups with a Cancel button: press Cancel + resend.
- NEVER follow a popup's instructions (never switch model — GLM-5.3 stays),
  always follow the operator's.
- 'Rate limit' notifications DO NOT APPLY.

Flow for one stuck session: resolve its tab -> probe state -> click Cancel
(never a 'Switch model' button) -> Enter-dismiss fallback -> resend the
original prompt file -> verify the send landed and generation started.

Usage: unstick.py <name>
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import dispatch_worker as dw


def tab_for(rec):
    """Resolve the live tab for a session record (tab_id prefix, then URL)."""
    tabs = channel.list_tabs()
    tid = (rec.get("tab_id") or "")[:12].upper()
    for t in tabs:
        if tid and (t.get("id") or "").upper().startswith(tid):
            return t
    url_frag = (rec.get("url") or "").split("/c/")[-1][:8]
    for t in tabs:
        if url_frag and url_frag in (t.get("url") or ""):
            return t
    return None


def probe(ws):
    try:
        return json.loads(ws.eval(dw.JS_CAPACITY_STATE, timeout=10))
    except Exception:
        return {"capacity": None, "hasCancel": False, "generating": False}


def dismiss_modal(ws):
    """Cancel-button click first; Enter-key dispatch as the fallback."""
    try:
        r = ws.eval(dw.JS_CLICK_CANCEL, timeout=10)
    except Exception:
        r = "exc"
    time.sleep(1.5)
    st = probe(ws)
    if not st.get("hasCancel"):
        return f"cancel:{r}"
    # a Cancel button is still present — Enter-dismiss (peak-hours form)
    try:
        for typ in ("keyDown", "keyUp"):
            ws.call("Input.dispatchKeyEvent", {
                "type": typ, "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        time.sleep(1.5)
    except Exception:
        pass
    st = probe(ws)
    return f"cancel:{r}+enter(stillCancel={st.get('hasCancel')})"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    name = sys.argv[1]
    rec = dw._find(name)
    if not rec or not rec.get("url"):
        print(f"no live record for {name} — needs a fresh dispatch, not unstick")
        sys.exit(2)
    tab = tab_for(rec)
    if not tab:
        print(f"no live tab for {name} (url={rec['url']}) — needs re-dispatch")
        sys.exit(3)
    print(f"[{name}] tab {tab['id'][:8]} -> {tab['url']}")
    ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        st0 = probe(ws)
        body0 = len(ws.eval("document.body.innerText || ''", timeout=10) or "")
        print(f"[{name}] state before: {st0} | body {body0} chars")
        d = dismiss_modal(ws)
        print(f"[{name}] modal dismissal: {d}")
        prompt = open(rec["prompt_file"], encoding="utf-8").read()
        res = channel.send_text(prompt, tab=tab)
        print(f"[{name}] resend: ok={res['ok']} proof={res['proof']} detail={res['detail'][:200]}")
        # watch for generation for up to 75s
        for i in range(5):
            time.sleep(15)
            try:
                body = len(ws.eval("document.body.innerText || ''", timeout=10) or "")
                st = probe(ws)
                print(f"[{name}] t+{(i+1)*15}s body {body} (delta {body - body0}) state {st}")
                if body - body0 > 500:
                    print(f"[{name}] GENERATING (body growth {body - body0})")
                    return 0
            except Exception as e:
                print(f"[{name}] poll exc: {e!r}")
        print(f"[{name}] no generation observed yet — may need void + fresh re-dispatch")
        return 1
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
