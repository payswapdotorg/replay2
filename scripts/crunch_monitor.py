#!/usr/bin/env python3
"""crunch_monitor.py — detached server-side truth monitor for the 2026-09-27
wave-3 capacity crunch.

Every CHECK_EVERY seconds, probe the three wave-3 chats server-side (from a
live chat.z.ai tab's auth context) and log STATUS TRANSITIONS only:
  - wedged-chat recovery:  http-500 -> readable (n, roles)
  - canary generation:     T006-3 msgs grows past 1 / assistant role appears
  - anything readable:     title/n/roles/updated deltas

Exit conditions: none (runs until killed). The Tech Lead lifts the outage
hold based on this log: capacity is back when (a) the canary fires, or
(b) the wedged chats read 200 again AND no capacity popup is sighted.

Usage: nohup python3 crunch_monitor.py > /tmp/crunch_monitor.log 2>&1 &
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

CHATS = {
    "T005-3": "1d5e2743-6cdd-4944-ac51-dada2996eb33",
    "T006-3": "f71dda4b-84c0-4d54-bf2f-ac4826c93339",
    "T007-3": "26153daa-6d79-4d8e-b9f4-9cda73f32d6c",
}
CHECK_EVERY = 300  # 5 min

JS = """(async () => {
  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
  const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
  const out = {};
  for (const [k, cid] of %s) {
    try {
      const r = await fetch('/api/v1/chats/' + cid, {credentials: 'include', cache: 'no-store', headers: hdr});
      if (!r.ok) { out[k] = 'http-' + r.status; continue; }
      const j = await r.json();
      const d = j.data || j;
      const h = ((d.chat || {}).history) || {};
      const msgs = h.messages || {};
      const ids = Object.keys(msgs);
      const roles = ids.map(i => msgs[i].role).join(',');
      out[k] = 'ok n=' + ids.length + ' roles=' + roles + ' upd=' + d.updated_at + ' title=' + (d.title||'').slice(0,22);
    } catch (e) { out[k] = 'exc:' + e.message; }
  }
  return JSON.stringify(out);
})()"""


def stamp():
    return time.strftime("%H:%M:%S")


def main():
    last = {}
    print(f"[crunch] {stamp()} monitor up (every {CHECK_EVERY}s)", flush=True)
    while True:
        try:
            tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "") and "/c/" in (t.get("url") or "")]
            if not tabs:
                tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
            if not tabs:
                print(f"[crunch] {stamp()} no chat tab available", flush=True)
                time.sleep(CHECK_EVERY)
                continue
            ws = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=30)
            try:
                raw = ws.eval(JS % json.dumps(list(CHATS.items())), await_promise=True, timeout=45)
                d = json.loads(raw)
            finally:
                ws.close()
            for k, v in d.items():
                if last.get(k) != v:
                    print(f"[crunch] {stamp()} {k}: {v}", flush=True)
                    last[k] = v
        except Exception as e:
            print(f"[crunch] {stamp()} loop-error {type(e).__name__}: {e}", flush=True)
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
