#!/usr/bin/env python3
"""staged_send_loop.py <tab_prefix> <chat_uuid> <min_staged_chars> <rounds>
Cancel (never Flash-switch) + re-Enter the staged composer until the chat's
server-side tree grows past baseline. Ground truth = chats API count."""
import json, sys, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

TABP, CHAT = sys.argv[1], sys.argv[2]
MINC, ROUNDS = int(sys.argv[3]), int(sys.argv[4])

def get_tab():
    return next((t for t in channel.list_tabs() if t["id"].startswith(TABP)), None)

def tree_probe():
    js = f"""
    (async () => {{
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/chats/{CHAT}', {{credentials:'include', headers: {{'Authorization': 'Bearer ' + t}}}});
      if (!r.ok) return 'HTTP' + r.status;
      const d = await r.json();
      const h = (d.chat || {{}}).history || {{}};
      return String(Object.keys(h.messages || {{}}).length);
    }})()
    """
    t = channel.find_tab("chat.z.ai/")
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        return ws.eval(js, await_promise=True, timeout=45)
    finally:
        ws.close()

def dismiss_modal(cdp):
    return cdp.eval(r"""(() => {
      for (const el of document.querySelectorAll('div,section,[role=dialog]')) {
        const st = getComputedStyle(el);
        if ((st.position === 'fixed' || st.position === 'absolute') && parseInt(st.zIndex || '0') >= 200) {
          const txt = (el.innerText || '');
          if (txt.includes('peak hours') || txt.includes('capacity') || txt.includes('personal limit') || txt.includes('limit')) {
            const c = Array.from(el.querySelectorAll('button')).find(b => (b.innerText||'').trim() === 'Cancel');
            if (c) { c.click(); return 'cancelled'; }
            return 'no-cancel';
          }
        }
      }
      return 'none';
    })()""", await_promise=False, timeout=20)

def composer_len(cdp):
    v = cdp.eval("(document.querySelector('#chat-input, textarea') || {value:''}).value.length", await_promise=False, timeout=15)
    return v or 0

def enter(cdp):
    ta = cdp.eval(r"""(() => {
      const ta = document.querySelector('#chat-input, textarea');
      if (ta) { ta.focus(); return 'focused'; }
      return 'none';
    })()""", await_promise=False, timeout=15)
    for typ in ("keyDown", "keyUp"):
        cdp.call("Input.dispatchKeyEvent", {
            "type": typ, "key": "Enter", "code": "Enter",
            "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    return ta

def main():
    base = tree_probe()
    print(f"baseline tree: {base}")
    for rnd in range(1, ROUNDS + 1):
        tab = get_tab()
        if not tab:
            print(f"round {rnd}: tab lost"); return 1
        cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=45)
        try:
            dm = dismiss_modal(cdp)
            cl = composer_len(cdp)
            print(f"round {rnd}: modal={dm} composer={cl}", flush=True)
            if cl < MINC:
                print(f"round {rnd}: composer lost the staged message — STOP (needs re-insert)")
                return 3
            if dm == "cancelled":
                time.sleep(2.5)
                cl2 = composer_len(cdp)
                if cl2 < MINC:
                    print(f"round {rnd}: staged message lost after cancel — STOP")
                    return 3
            enter(cdp)
            time.sleep(5)
            dm2 = dismiss_modal(cdp)
            if dm2 == "cancelled":
                time.sleep(2)
            try:
                n = tree_probe()
            except Exception as e:
                print(f"round {rnd}: probe failed {type(e).__name__}"); time.sleep(4); continue
            print(f"round {rnd}: tree={n}", flush=True)
            if n.isdigit() and base.isdigit() and int(n) > int(base):
                print(f"SENT VERIFIED SERVER-SIDE (tree {base} -> {n})")
                return 0
            if n.startswith("HTTP"):
                pass  # chat not yet created server-side; keep trying
        finally:
            cdp.close()
        time.sleep(5)
    print("exhausted rounds")
    return 2

if __name__ == "__main__":
    sys.exit(main())
