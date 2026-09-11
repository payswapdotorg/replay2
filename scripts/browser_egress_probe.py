#!/usr/bin/env python3
"""browser_egress_probe.py — measures the CHROME browser's egress IP.

Why not a python-side probe: the TurboVPN Chrome extension is a
proxy-based VPN — it routes the BROWSER's traffic, not the python
process's. A python urllib probe would never see the VPN turn on.
This probe evaluates fetch() INSIDE a browser tab via CDP, so the
reading reflects the extension proxy the moment it routes traffic.

Every 60s it:
  - picks a tab (preference: chrome-extension:// popup > chat.z.ai > any
    page — extension pages have host_permissions so CORS never blocks),
  - evaluates fetch('https://api.ipify.org') (fallback ifconfig.me),
  - validates the result looks like an IP,
  - appends one line to /tmp/browser_egress.log,
  - refreshes flags/vpn_state.json {"ip","ts","tab"}.

Markers:
  BASELINE <ip>                  first reading
  NEW-BROWSER-EGRESS-IP a -> b   VPN toggled (extension connect/disconnect)
  ERR <reason>                   probe failure (kept going, never dies)

On NEW-BROWSER-EGRESS-IP it also appends an operator-inbox-format notice
to flags/agent_outbox.jsonl (same append-only format the resident uses)
so the console message thread surfaces the transition immediately.

Never sends anything into any chat site. Pure observation.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
LOG = "/tmp/browser_egress.log"
STATE = os.path.join(FLAGS, "vpn_state.json")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
INTERVAL = 60

IP_RE = re.compile(r"^[0-9a-fA-F.:.]{3,45}$")

FETCH_JS = (
    "fetch('https://api.ipify.org',{cache:'no-store'})"
    ".then(r=>r.text()).then(t=>t.trim())"
)
FETCH_JS2 = (
    "fetch('https://ifconfig.me/ip',{cache:'no-store'})"
    ".then(r=>r.text()).then(t=>t.trim())"
)


def log(line):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S UTC") + " " + line + "\n")


def outbox(text):
    try:
        with open(OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent",
                                "text": str(text)[:2000]}) + "\n")
    except Exception:
        pass


def pick_tab():
    """chrome-extension popup > chat.z.ai > any page tab."""
    tabs = channel.list_tabs()
    if not tabs:
        return None
    for t in tabs:
        if (t.get("url") or "").startswith("chrome-extension://"):
            return t
    for t in tabs:
        if "chat.z.ai" in (t.get("url") or ""):
            return t
    return tabs[0]


def read_ip(tab):
    ws = tab.get("webSocketDebuggerUrl")
    if not ws:
        raise RuntimeError("no-ws-url")
    cdp = channel.CDP(ws, timeout=20)
    try:
        for js in (FETCH_JS, FETCH_JS2):
            try:
                v = cdp.eval(js, await_promise=True, timeout=20)
                if isinstance(v, str):
                    v = v.strip()
                    if v and IP_RE.match(v) and " " not in v and "<" not in v:
                        return v
            except Exception:
                continue
        raise RuntimeError("fetch-failed")
    finally:
        cdp.close()


def write_state(ip, tab):
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump({"ip": ip,
                       "ts": time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                       "tab": (tab.get("url") or "")[:120]}, f)
    except Exception:
        pass


def main():
    log("probe start (browser-side egress, 60s cycle)")
    last = None
    while True:
        try:
            tab = pick_tab()
            if not tab:
                log("ERR no-tabs")
            else:
                ip = read_ip(tab)
                write_state(ip, tab)
                if last is None:
                    last = ip
                    log(f"BASELINE {ip}")
                elif ip != last:
                    log(f"NEW-BROWSER-EGRESS-IP {last} -> {ip}")
                    outbox(f"Browser egress IP changed: {last} -> {ip}. "
                           "If TurboVPN was just connected this is the VPN "
                           "taking over routing — generation egress may be "
                           "unblocked now.")
                    last = ip
                else:
                    log(f"ip {ip} (unchanged)")
        except Exception as e:
            log(f"ERR {e!r}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
