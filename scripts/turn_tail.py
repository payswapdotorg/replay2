#!/usr/bin/env python3
"""turn_tail.py — dump the TAIL of a chat's assistant work-log (batch store).

Forensic companion to probe_chat.py: the batch store holds the streamed
Agents-tab work log; this prints the last N chars of the latest assistant
batch message (content_blocks joined) so a resident watcher can tell
  frozen-mid-work  vs  clean-stop  vs  report-landed
without opening a tab. Also prints block count and total chars.

Usage: turn_tail.py <chat-id> [tail-chars=2000]
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cid = sys.argv[1]
    tail_n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000

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
          const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
          const r = await fetch('/api/v1/chats/%s', {credentials: 'include', cache: 'no-store', headers: hdr});
          if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
          const j = await r.json();
          const msgs = ((j.chat || {}).history || {}).messages || {};
          const byTs = Object.values(msgs).sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
          const ids = byTs.map(m => m.id).filter(Boolean);
          if (!ids.length) return JSON.stringify({err: 'no messages'});
          const br = await fetch('/api/v1/chats/%s/messages/batch', {
            credentials: 'include', cache: 'no-store', method: 'POST',
            headers: Object.assign({'Content-Type': 'application/json'}, hdr),
            body: JSON.stringify({ids})});
          if (!br.ok) return JSON.stringify({err: 'batch-http-' + br.status});
          const bj = await br.json();
          const data = (bj && (bj.data || bj.messages)) || {};
          const out = [];
          for (const id of ids) {
            const m = data[id];
            if (!m || (m.role || 'assistant') === 'user') continue;
            const blocks = m.content_blocks || m.blocks || [];
            let txt = '';
            for (const b of blocks) {
              txt += (b && (b.text || b.content || '')) || '';
              txt += '\\n';
            }
            if (!txt) {
              const c = m.content;
              txt = Array.isArray(c) ? c.map(x => (x && (x.text || '')) || '').join('\\n')
                                     : (typeof c === 'string' ? c : '');
            }
            out.push({ts: m.timestamp || m.ts || 0, blocks: blocks.length, chars: txt.length, txt});
          }
          return JSON.stringify({title: j.title, updated: j.updated_at, turns: out});
        })()""" % (cid, cid)
        raw = ws.eval(js, await_promise=True, timeout=45)
        d = json.loads(raw)
        if d.get("err"):
            print(json.dumps(d))
            return 2
        print("title:", (d.get("title") or "")[:60], "| updated:", d.get("updated"))
        turns = d.get("turns") or []
        if not turns:
            print("no assistant turns in batch store")
            return 0
        for t in turns:
            print(f"--- assistant turn: blocks={t['blocks']} chars={t['chars']} ts={t['ts']}")
            txt = t.get("txt") or ""
            print(f"[tail {min(tail_n, len(txt))} chars]")
            print(txt[-tail_n:])
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"err": str(e)[:160]}))
        sys.exit(3)
