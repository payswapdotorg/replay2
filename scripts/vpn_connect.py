#!/usr/bin/env python3
"""vpn_connect.py — one-shot TurboVPN connect/recover via the extension popup.

Lesson-72 procedure automated (2026-09-12 19:40 field-proven): the extension
popup tab is the control surface. If the popup shows CONNECTED but the
browser egress is dead (the known dead-tunnel state: fetch-failed in the
egress probe while the popup timer still runs), TOGGLE the power control
(disconnect -> reconnect) — a plain re-check does not heal it.

Usage:
  python3 vpn_connect.py            # heal/connect + verify egress
  python3 vpn_connect.py status     # report popup state + egress only
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

EXT_ID = "piplkafkogjfjlofefcobgiccagncean"
POPUP_URL = f"chrome-extension://{EXT_ID}/dist/popup/index.html"


def popup_tab():
    t = next((x for x in channel.list_tabs() if EXT_ID in (x.get("url") or "")), None)
    if t is None:
        t = channel.new_tab("about:blank")
        time.sleep(2)
        if t:
            # /json/new?url=... no longer navigates (Chrome 151): do it via CDP
            try:
                cdp = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
                try:
                    cdp.call("Page.navigate", {"url": POPUP_URL}, timeout=30)
                finally:
                    cdp.close()
            except Exception:
                pass
            time.sleep(6)
    return t


def popup_state(cdp):
    return cdp.eval(r"""(() => {
      const body = document.body.innerText || '';
      const power = document.querySelector('.mt-5.w-16.h-16.cursor-pointer');
      return JSON.stringify({connected: body.includes('CONNECTED'), hasPower: !!power});
    })()""", await_promise=False, timeout=20)


def click_power(cdp):
    return cdp.eval(r"""(() => {
      const p = document.querySelector('.mt-5.w-16.h-16.cursor-pointer');
      if (!p) return 'no-power';
      p.click(); return 'clicked';
    })()""", await_promise=False, timeout=20)


def egress(cdp, tries=3):
    js = r"""(async () => {
      try {
        const r = await fetch('https://api.ipify.org?format=json', {cache: 'no-store'});
        return 'EGRESS ' + (await r.json()).ip;
      } catch (e) { return 'ERR ' + e.message; }
    })()"""
    out = "ERR no-attempt"
    for _ in range(tries):
        out = cdp.eval(js, await_promise=True, timeout=45)
        if str(out).startswith("EGRESS"):
            return out
        time.sleep(6)
    return out


def main():
    status_only = len(sys.argv) > 1 and sys.argv[1] == "status"
    tab = popup_tab()
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        state = json.loads(popup_state(cdp) or "{}")
        print("popup:", state)
        # egress via the chat.z.ai HOME tab (root URL — worker-chat renderers
        # stream constantly and time CDP evals out; the root tab is idle)
        tabs = channel.list_tabs()
        chat = next((x for x in tabs if (x.get("url") or "").rstrip("/").endswith("chat.z.ai")), None) \
            or next((x for x in tabs if "chat.z.ai" in (x.get("url") or "")), None)
        chat_cdp = channel.CDP(chat["webSocketDebuggerUrl"], timeout=60) if chat else None
        try:
            if status_only:
                print("egress:", egress(chat_cdp) if chat_cdp else "no chat tab")
                return 0
            if not state.get("hasPower"):
                print("ERROR: power control not found in popup")
                return 2
            if state.get("connected"):
                eg = egress(chat_cdp) if chat_cdp else "ERR no-chat-tab"
                print("connected; egress:", eg)
                if str(eg).startswith("EGRESS"):
                    print("HEALTHY")
                    return 0
                # dead-tunnel state: toggle to heal
                print("dead tunnel — toggling power")
                click_power(cdp)
                time.sleep(6)
                print("after disconnect:", popup_state(cdp))
            click_power(cdp)
            time.sleep(10)
            print("after reconnect:", popup_state(cdp))
            eg = egress(chat_cdp) if chat_cdp else "ERR no-chat-tab"
            print("egress:", eg)
            print("RECOVERED" if str(eg).startswith("EGRESS") else "STILL-DOWN")
            return 0 if str(eg).startswith("EGRESS") else 3
        finally:
            if chat_cdp:
                chat_cdp.close()
    finally:
        cdp.close()


if __name__ == "__main__":
    sys.exit(main())
