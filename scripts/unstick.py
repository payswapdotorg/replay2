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

BASE = os.path.dirname(os.path.abspath(__file__))


def prompt_file_for(name):
    """Registry-first prompt lookup with case-tolerant staged fallback.

    2026-09-27 fix (TradRL T006): BASE was referenced here but never defined
    — the unstick crashed with NameError BEFORE the resend, leaving the
    modal dismissed but no new generation attempt. Also try the UPPERCASE
    staged variant (queue_watch lesson-58 lineage) before giving up.
    """
    for s in dw._sessions():
        if s.get("name") == name and s.get("prompt_file"):
            if os.path.exists(s["prompt_file"]):
                return s["prompt_file"]
    for cand in (os.path.join(BASE, "worker-prompts", f"{name}.md"),
                 os.path.join(BASE, "worker-prompts", f"{name.upper()}.md")):
        if os.path.exists(cand):
            return cand
    return None


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


def dismiss_modal(ws, agent_lane=False):
    """Cancel-button click first; Enter-key dispatch as the fallback.

    LESSON 185 (2026-09-27): on AGENT lanes a Cancel click on the peak popup
    KILLS THE SESSION (observed: cancel -> promo interstitial -> /c/ URL
    bounces home forever). The agent-lane dismissal is a PAGE RELOAD — it
    clears the popup visual and keeps the queued turn server-side. Never
    click Cancel on an agents-tab session.
    """
    if agent_lane:
        try:
            ws.call("Page.enable")
            ws.call("Page.reload")
            time.sleep(3.0)
        except Exception as e:
            return f"reload-exc:{type(e).__name__}"
        st = probe(ws)
        return f"reload(cancel-cleared={not st.get('hasCancel')})"
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
    # LESSON 185: agent-lane sessions must never be Cancel-clicked. The
    # registry's latest record carries the mode the dispatcher verified at
    # create time (agents-tab) — a chip reset by a rollback does NOT demote
    # the conversation, so registry truth wins over DOM chips.
    agent_lane = (rec.get("mode") == "agents-tab")
    print(f"[{name}] lane: {'AGENT (reload-only dismissal)' if agent_lane else 'chat (cancel+resend ok)'}")
    if agent_lane:
        # An agent session holding a VERIFIED send with a cosmetic popup must
        # NOT be resent either — the queued turn drains on its own. Reload
        # clears the visual; report and exit without touching the composer.
        tab = tab_for(rec)
        if not tab:
            print(f"no live tab for {name} (url={rec['url']}) — needs re-dispatch")
            sys.exit(3)
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
        try:
            st0 = probe(ws)
            print(f"[{name}] state before: {st0}")
            if st0.get("hasCancel") or st0.get("capacity"):
                d = dismiss_modal(ws, agent_lane=True)
                print(f"[{name}] agent-lane dismissal (reload): {d}")
            else:
                print(f"[{name}] no blocking popup — nothing to unstick (lesson 185: wait for the generation window)")
            return 0
        finally:
            ws.close()
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
        # 2026-09-12 fix: tab-reopen records (registry re-aim) don't carry
        # prompt_file — _find only carries tab_id/url onto the resolved
        # record. Fall back to the canonical staged prompt path instead of
        # crashing with KeyError (the crash aborted the whole unstick).
        pf = rec.get("prompt_file") or prompt_file_for(name)
        if not pf:
            print(f"[{name}] NO PROMPT FILE (registry+staged) — cannot resend")
            return 1
        prompt = open(pf, encoding="utf-8").read()
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
