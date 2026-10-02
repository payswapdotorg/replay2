#!/usr/bin/env python3
"""netcheck.py — reload the chat tab, then test external egress + same-origin API."""
import sys, time, json
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

tab = channel.find_tab("chat.z.ai")
if tab is None:
    print("no chat tab"); sys.exit(1)
print("tab:", tab["id"][:8], (tab.get("url") or "")[:60])
ws = channel.CDP(tab["webSocketDebuggerUrl"])
try:
    ws.call("Page.enable", {})
    ws.call("Page.reload", {"ignoreCache": True})
    time.sleep(8)
    js = """(async () => {
      const out = {};
      try {
        const r = await fetch('https://api.ipify.org?format=json', {cache: 'no-store'});
        out.egress = (await r.json()).ip;
      } catch (e) { out.egress = 'ERR ' + String(e).slice(0, 60); }
      try {
        const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
        const r2 = await fetch('/api/v1/chats/list?page=1&size=3', {credentials: 'include', cache: 'no-store', headers: tok ? {Authorization: 'Bearer ' + tok} : {}});
        out.api = r2.ok ? 'ok-' + r2.status : 'http-' + r2.status;
      } catch (e) { out.api = 'ERR ' + String(e).slice(0, 60); }
      return JSON.stringify(out);
    })()"""
    print(ws.eval(js, await_promise=True, timeout=30))
finally:
    ws.close()
