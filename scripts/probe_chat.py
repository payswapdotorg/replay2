#!/usr/bin/env python3
"""probe_chat.py — SERVER-SIDE truth prober for a chat session.

The DOM lies (lesson 63/65: optimistic staging, wedged renderers, phantom
URLs); the chats API message tree is the only commit truth. This probe
answers, for any chat id:
  - does the chat exist?
  - last N messages (role, content length, timestamp)
  - is an assistant message carrying the report marker?
  - updated_at age (turn activity)

Usage: probe_chat.py <chat-id> [marker-substring, default COMPLETION REPORT]
Prints one JSON line. Exit codes: 0=chat alive, 2=chat not found.
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cid = sys.argv[1]
    marker = sys.argv[2] if len(sys.argv) > 2 else "COMPLETION REPORT"
    # prefer a tab already ON this chat (its renderer has the freshest auth
    # context); fall back to any chat.z.ai tab
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    target = None
    for t in tabs:
        if cid[:8] in (t.get("url") or ""):
            target = t
            break
    if target is None:
        target = tabs[-1] if tabs else None
    if target is None:
        print(json.dumps({"err": "no chat.z.ai tab"}))
        return 2
    ws = channel.CDP(target["webSocketDebuggerUrl"])
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
          const r = await fetch('/api/v1/chats/%s', {credentials: 'include',
            headers: tok ? {Authorization: 'Bearer ' + tok} : {}});
          if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
          const j = await r.json();
          const msgs = ((j.chat || {}).history || {}).messages || {};
          const byTs = Object.values(msgs).sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
          const last = [];
          for (const m of byTs.slice(-4)) {
            const c = Array.isArray(m.content) ? m.content : [m.content];
            const txt = JSON.stringify(c);
            last.push({role: m.role, len: txt.length, ts: m.timestamp,
                       hasMarker: txt.indexOf(%s) >= 0});
          }
          let reportInAssistant = false;
          for (const m of byTs) {
            if (m.role !== 'assistant') continue;
            const c = Array.isArray(m.content) ? m.content : [m.content];
            if (JSON.stringify(c).indexOf(%s) >= 0) reportInAssistant = true;
          }
          return JSON.stringify({alive: true, title: j.title, updated: j.updated_at,
            now: Math.floor(Date.now() / 1000), msgs: byTs.length,
            last, reportInAssistant});
        })()""" % (cid, json.dumps(marker), json.dumps(marker))
        raw = ws.eval(js, await_promise=True, timeout=30)
        d = json.loads(raw)
        print(json.dumps(d))
        return 0 if d.get("alive") else 2
    finally:
        ws.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"err": str(e)[:120]}))
        sys.exit(3)
