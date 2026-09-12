#!/usr/bin/env python3
"""val014_resend.py — robust resend of the Lead transcripts message into the
val-014 worker chat (41aff710). Never uses form.requestSubmit (navigates away).
Submit = send-button click, Enter fallback. Dismisses peak-hours modal with
Cancel (NEVER the Flash switch). Ground truth = chats API message count."""
import json, sys, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

CHAT = "41aff710-bc3e-40af-96fe-a5fb653edece"
TAB_PREFIX = "05161674C943"
MSG = open("/tmp/val014_transcripts.md").read()
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8

def get_tab():
    return next((t for t in channel.list_tabs() if t["id"].startswith(TAB_PREFIX)), None)

def api_tab():
    return channel.find_tab("chat.z.ai/")

def tree_count():
    js = f"""
    (async () => {{
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/chats/{CHAT}', {{credentials:'include', headers: {{'Authorization': 'Bearer ' + t}}}});
      const d = await r.json();
      const h = (d.chat || {{}}).history || {{}};
      return String(Object.keys(h.messages || {{}}).length);
    }})()
    """
    t = api_tab()
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        return int(ws.eval(js, await_promise=True, timeout=45) or 0)
    finally:
        ws.close()

def dismiss_modal(cdp):
    return cdp.eval(r"""(() => {
      for (const el of document.querySelectorAll('div,section,[role=dialog]')) {
        const st = getComputedStyle(el);
        if ((st.position === 'fixed' || st.position === 'absolute') && parseInt(st.zIndex || '0') >= 200) {
          const txt = (el.innerText || '');
          if (txt.includes('peak hours') || txt.includes('capacity') || txt.includes('personal limit')) {
            const c = Array.from(el.querySelectorAll('button')).find(b => (b.innerText||'').trim() === 'Cancel');
            if (c) { c.click(); return 'cancelled-modal'; }
            return 'modal-no-cancel';
          }
        }
      }
      return 'no-modal';
    })()""", await_promise=False, timeout=20)

def navigate_to_chat(cdp):
    return cdp.eval(f"location.href = 'https://chat.z.ai/c/{CHAT}'; 'nav'", await_promise=False, timeout=15)

def wait_composer(cdp, tries=30):
    for _ in range(tries):
        r = cdp.eval(r"""(() => {
          const ta = document.querySelector('#chat-input, textarea');
          return ta ? JSON.stringify({len: (ta.value||'').length, w: ta.getBoundingClientRect().width}) : 'none';
        })()""", await_promise=False, timeout=15)
        if r and r != "none":
            return json.loads(r)
        time.sleep(1.5)
    return None

def insert_msg(cdp):
    cdp.eval(r"""(() => {
      const ta = document.querySelector('#chat-input, textarea');
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, '');
      ta.dispatchEvent(new Event('input', {bubbles: true}));
    })()""", await_promise=False, timeout=15)
    time.sleep(0.4)
    cdp.call("Input.insertText", {"text": MSG})
    time.sleep(0.8)
    v = cdp.eval("(document.querySelector('#chat-input, textarea') || {value:''}).value.length", await_promise=False, timeout=15)
    return v or 0

def submit_msg(cdp):
    # send button first
    r = cdp.eval(r"""(() => {
      const btn = [...document.querySelectorAll('button')].find(b => {
        const al = (b.getAttribute('aria-label') || '').toLowerCase();
        return al.includes('send') || al.includes('submit');
      });
      if (btn && !btn.disabled) { btn.click(); return 'btn'; }
      return 'nobtn';
    })()""", await_promise=False, timeout=20)
    if r == "btn":
        return "send-button"
    # Enter fallback on the textarea
    for typ in ("keyDown", "keyUp"):
        cdp.call("Input.dispatchKeyEvent", {
            "type": typ, "key": "Enter", "code": "Enter",
            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    return "enter"

def main():
    n0 = tree_count()
    print(f"baseline tree: {n0} messages")
    for rnd in range(1, ROUNDS + 1):
        tab = get_tab()
        if not tab:
            print(f"round {rnd}: tab lost"); return 1
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=45)
        try:
            url = cdp.eval("location.href", await_promise=False, timeout=15) or ""
            if f"/c/{CHAT[:8]}" not in url:
                print(f"round {rnd}: navigating (at {url[:50]})")
                navigate_to_chat(cdp)
                time.sleep(6)
            comp = wait_composer(cdp)
            if not comp:
                print(f"round {rnd}: no composer"); time.sleep(3); continue
            if comp["len"] < 40:
                got = insert_msg(cdp)
                print(f"round {rnd}: inserted {got} chars")
                if got < 40:
                    print(f"round {rnd}: insert failed"); time.sleep(3); continue
            dm = dismiss_modal(cdp)
            if dm != "no-modal":
                print(f"round {rnd}: {dm}; waiting for modal transition")
                time.sleep(2.5)
                # re-check composer still holds the message
                comp2 = wait_composer(cdp, tries=8)
                if not comp2 or comp2["len"] < 40:
                    print(f"round {rnd}: message lost after modal cancel; re-insert")
                    got = insert_msg(cdp)
                    if got < 40: continue
            how = submit_msg(cdp)
            time.sleep(4)
            dm2 = dismiss_modal(cdp)
            print(f"round {rnd}: submitted via {how}; post-submit modal: {dm2}")
            time.sleep(3)
            try:
                n = tree_count()
            except Exception as e:
                print(f"round {rnd}: tree check failed {type(e).__name__}"); continue
            print(f"round {rnd}: tree now {n} messages", flush=True)
            if n > n0:
                print(f"SENT VERIFIED SERVER-SIDE (tree {n0} -> {n})")
                return 0
        finally:
            cdp.close()
        time.sleep(5)
    print("exhausted rounds without server-side confirmation")
    return 2

if __name__ == "__main__":
    sys.exit(main())
