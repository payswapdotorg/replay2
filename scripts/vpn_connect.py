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
import hashlib
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import channel  # noqa: E402


def derive_ext_id(ext_dir: str) -> str:
    """Unpacked-extension ID = first 32 sha256(path) hex chars, 0-f -> a-p.

    Deriving from the ACTUAL checkout path (not a hardcoded ID) is the fix
    for the 2026-09-28 stale-ID defect: the old script pinned the ID of the
    pre-reset /home/z/replay2 checkout (piplkafkogj...), which Chromium
    ERR_BLOCKED_BY_CLIENT-blocks when a tab is navigated to it, while the
    live extension loaded from THIS checkout has a different, valid ID.
    """
    h = hashlib.sha256(ext_dir.rstrip("/").encode()).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in h)


def _turbo_ext_dir() -> str:
    # launch_stack.py: EXT_ROOT = <scripts>/extensions — the extension lives
    # NEXT TO this script (scripts/extensions/turbovpn), not at checkout root
    return os.path.join(_HERE, "extensions", "turbovpn")


EXT_DIR = _turbo_ext_dir()
EXT_ID = derive_ext_id(EXT_DIR)
POPUP_URL = f"chrome-extension://{EXT_ID}/dist/popup/index.html"


def popup_tab():
    # match the POPUP page specifically (extension pages of the same ID like
    # dist/background also carry the ID in their URL)
    t = next(
        (x for x in channel.list_tabs()
         if (x.get("url") or "").startswith(f"chrome-extension://{EXT_ID}/dist/popup/")),
        None,
    )
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
      return JSON.stringify({connected: /connected|protecting/i.test(body),
                             hasPower: !!power});
    })()""", await_promise=False, timeout=20)


def click_power(cdp):
    """REAL mouse click via CDP Input.dispatchMouseEvent.

    The 'Tap to Connect' element ignores synthetic DOM .click() — the r30b
    field lesson (2026-09-16): only real mouse events at the button center
    trigger the extension's connect flow (the manual_send pattern).
    """
    rect = cdp.eval(r"""(() => {
      const p = document.querySelector('.mt-5.w-16.h-16.cursor-pointer');
      if (!p) return null;
      const r = p.getBoundingClientRect();
      return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
    })()""", await_promise=False, timeout=20)
    if not rect or rect == "null":
        return "no-power"
    d = json.loads(rect)
    for typ in ("mousePressed", "mouseReleased"):
        cdp.call("Input.dispatchMouseEvent", {
            "type": typ, "x": d["x"], "y": d["y"],
            "button": "left", "clickCount": 1})
    return "clicked"


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
        # egress via the POPUP renderer (2026-09-23: the chat home tab's
        # renderer gets WEDGED by outage retry-storms — its evals hang and
        # this check died with a websocket timeout instead of reporting;
        # the popup page is extension-local, never loads chat.z.ai JS, and
        # its fetch still goes through the process-wide tunnel)
        if status_only:
            print("egress:", egress(cdp))
            return 0
        if not state.get("hasPower"):
            print("ERROR: power control not found in popup")
            return 2
        if state.get("connected"):
            eg = egress(cdp)
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
        time.sleep(15)
        print("after reconnect:", popup_state(cdp))
        eg = egress(cdp)
        print("egress:", eg)
        print("RECOVERED" if str(eg).startswith("EGRESS") else "STILL-DOWN")
        return 0 if str(eg).startswith("EGRESS") else 3
    finally:
        cdp.close()


if __name__ == "__main__":
    sys.exit(main())
