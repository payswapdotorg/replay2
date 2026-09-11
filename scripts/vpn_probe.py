#!/usr/bin/env python3
"""vpn_probe.py — passive block/liveness probe for a worker session.

Background (operator finding, 2026-09-11): generation-queue rejections that
surface in-page as "No response, Please try again later." +
`SyntaxError: Unexpected token '<'` are IP/region-level; the fix is routing
the sandbox egress through a VPN. This probe NEVER sends anything into the
chat (failed generation attempts can re-arm cooldown windows — lesson 16).

Every 60s it records, one line to /tmp/vpn_probe.log:
  - egress IP (api.ipify.org, fallback ifconfig.me)  -> IP-CHANGE marker
  - watched session tab DOM state (len / STREAM / FINAL / ERR)
  - server-side session existence + message-chain count via in-page
    chats API (GET /api/v1/chats/<cid>, credentials:include)

Markers: IP-CHANGE (VPN toggled — retry generation once), SESSION-LOST
(chat destroyed — fresh dispatch needed), STREAM (generating), FINAL
(completion report visible), ERR (queue rejection still active).
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

CHAT_ID = "800dbe75-5c7f-4d01-9345-abd875e5aab3"
URL_MARK = "800dbe75"
LOG = "/tmp/vpn_probe.log"


def egress_ip():
    for url in ("https://api.ipify.org", "https://ifconfig.me"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=10) as r:
                ip = r.read().decode("utf-8", "replace").strip()
                if ip and len(ip) <= 45 and " " not in ip:
                    return ip
        except Exception:
            continue
    return "?"


def find_session_tab(tabs):
    for t in tabs:
        if t.get("type") == "page" and URL_MARK in (t.get("url") or ""):
            return t
    return None


def find_any_chat_tab(tabs):
    for t in tabs:
        if t.get("type") == "page" and "chat.z.ai" in (t.get("url") or ""):
            return t
    return None


def dom_state(tab):
    """Returns (chars, flag) — flag in STREAM/FINAL/ERR/IDLE/WEDGED."""
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            body = c.eval("document.body.innerText || ''") or ""
        finally:
            c.close()
        tail = body[-800:]
        if "Thought Process" in body[-3000:] or "Deep Think" in body[-3000:]:
            return len(body), "STREAM"
        if "FINAL REPORT" in body and len(body) > 8000:
            return len(body), "FINAL"
        if ("personal limit" in tail or "at capacity" in tail
                or "No response" in tail or "try again later" in tail):
            return len(body), "ERR"
        return len(body), "IDLE"
    except Exception:
        return -1, "WEDGED"


def chat_api_state(tab):
    """Server-side truth via in-page fetch. Returns 'n=<count>' or LOST/ERR."""
    js = f"""
    (async () => {{
      try {{
        const r = await fetch('/api/v1/chats/{CHAT_ID}',
                               {{credentials: 'include'}});
        const t = await r.text();
        if (!r.ok || t.slice(0, 1) === '<') return 'HTTP' + r.status + ':HTML';
        const d = JSON.parse(t);
        const hist = ((d.chat) || {{}}).history || {{}};
        const mmap = hist.messages;
        if (!mmap) return 'n=?';
        const roots = Object.values(mmap).filter(m => !m.parentId);
        let n = 0, cur = roots[0];
        while (cur) {{ n += 1; const kids = cur.childrenIds || [];
            cur = kids.length ? mmap[kids[kids.length - 1]] : null; }}
        return 'n=' + n;
      }} catch (e) {{ return 'ERR:' + (e && e.message ? e.message : e); }}
    }})()
    """
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            val = c.eval(js, await_promise=True, timeout=30)
        finally:
            c.close()
        return str(val)
    except Exception as e:
        return "ERR-cdp:" + type(e).__name__


def main():
    known_ips = set()
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    logf = open(LOG, "a", buffering=1)
    logf.write(f"{time.strftime('%H:%M:%S')} vpn_probe started "
               f"(chat={CHAT_ID[:8]})\n")

    def emit(line):
        print(line, flush=True)
        logf.write(line + "\n")

    emit(f"{time.strftime('%H:%M:%S')} vpn_probe running "
         f"(pid {os.getpid()})")
    while True:
        ts = time.strftime("%H:%M:%S")
        ip = egress_ip()
        ip_note = ""
        if ip != "?" and ip not in known_ips:
            if known_ips:
                ip_note = (f"  *** NEW-EGRESS-IP {ip} "
                           f"(VPN? known={sorted(known_ips)}) ***")
            known_ips.add(ip)
        try:
            tabs = json.load(urllib.request.urlopen(
                "http://127.0.0.1:9222/json/list", timeout=10))
        except Exception as e:
            emit(f"{ts} ip={ip} TABS-ERR:{type(e).__name__}")
            time.sleep(60)
            continue
        stab = find_session_tab(tabs)
        if stab:
            chars, flag = dom_state(stab)
        else:
            chars, flag = -1, "TAB-LOST"
        api = "no-tab"
        anytab = stab or find_any_chat_tab(tabs)
        if anytab:
            api = chat_api_state(anytab)
            if "HTTP4" in api or "HTTP5" in api or ":HTML" in api \
                    or "not found" in api.lower():
                api += " SESSION-LOST?"
        emit(f"{ts} ip={ip} dom={chars}/{flag} chat={api}{ip_note}")
        time.sleep(60)


if __name__ == "__main__":
    main()
