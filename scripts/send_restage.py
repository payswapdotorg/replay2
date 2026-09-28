#!/usr/bin/env python3
"""send_restage.py <chat-id> <prompt-file> — open tab, dismiss popups, insert,
send, verify the message rendered in the chat DOM, close tab. Short-budget
surgical send (no long watch loop — the tl2_surge_watch handles the rest)."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel
from channel import CDP
import resend_prompt as rp


def main():
    cid = sys.argv[1]
    prompt = open(sys.argv[2]).read()
    tab = channel.new_tab(f"https://chat.z.ai/c/{cid}")
    if tab is None:
        print("SEND-FAIL: no tab")
        return 2
    time.sleep(6)
    cdp = CDP(tab["webSocketDebuggerUrl"], timeout=30)
    before = cdp.eval("document.body.innerText || ''", timeout=25) or ""
    # pre-flight: dismiss dialog / cancel capacity popup (doctrine)
    d = cdp.eval(rp.JS_DISMISS_DIALOG, timeout=10)
    if d not in ("none",):
        print("dialog dismissed:", d)
        time.sleep(0.8)
    try:
        st = json.loads(cdp.eval(rp.JS_STATE, timeout=15))
        if st.get("capacity") and st.get("hasCancel"):
            print("capacity popup -> Cancel (doctrine)")
            cdp.eval(rp.JS_CLICK_CANCEL, timeout=10)
            time.sleep(1.0)
    except Exception as e:
        print("state check err:", e)
    # insert + send
    pct = rp.insert_and_send(cdp, prompt)
    print(f"insert ratio {pct}%")
    time.sleep(6)
    after = cdp.eval("document.body.innerText || ''", timeout=25) or ""
    landed = any(k in after for k in ("TL follow-up", "RESTAGED", "WORKSPACE-LOST")) \
        and len(after) > len(before)
    print(f"before={len(before)} after={len(after)} landed={landed}")
    print("tail:", repr(after[-160:].replace("\n", " | ")))
    cdp.close()
    import urllib.request
    urllib.request.urlopen(f"http://127.0.0.1:9222/json/close/{tab['id']}", timeout=5).read()
    print("SEND-VERDICT:", "LANDED" if landed else "CHECK-MANUALLY")
    return 0 if landed else 1


if __name__ == "__main__":
    raise SystemExit(main())
