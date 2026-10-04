#!/usr/bin/env python3
"""tree_probe.py — server-side tree check from a DEDICATED home tab.

The worker tabs are work-rich (renderer saturated, §11a); find_tab grabs
the first chat.z.ai tab which may be one of them and evals time out.
This probe keeps its OWN lightweight tab (about:blank → chat.z.ai home)
and runs the chats-API fetches there. Usage: tree_probe.py <chat-uuid>
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import channel  # noqa: E402

PROBE_URL = "https://chat.z.ai/"


def probe(cid):
    tab = channel.new_tab(PROBE_URL)
    if tab is None:
        raise RuntimeError("probe tab failed")
    time.sleep(6)
    tabs = {t["id"]: t for t in channel.list_tabs()}
    t = tabs.get(tab["id"], tab)
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
    try:
        js = f"""
        (async () => {{
          const t0 = localStorage.getItem('token') || '';
          const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include', headers: {{'Authorization': 'Bearer ' + t0}}}});
          const d = await r.json();
          const hist = (d.chat || {{}}).history || {{}};
          const mmap = hist.messages || {{}};
          const msgs = Object.values(mmap);
          const roles = {{}};
          let newestTs = 0;
          for (const m of msgs) {{
            roles[m.role] = (roles[m.role] || 0) + 1;
            if ((m.timestamp || 0) > newestTs) newestTs = m.timestamp || 0;
          }}
          return JSON.stringify({{total: msgs.length, roles, newestTs, updated_at: (d.chat||{{}}).updated_at}});
        }})()
        """
        return ws.eval(js, await_promise=True, timeout=90)
    finally:
        ws.close()
        try:
            channel._http_json("/json/close/" + t["id"], method="PUT")
        except Exception:
            pass


if __name__ == "__main__":
    print(probe(sys.argv[1]))
