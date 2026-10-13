#!/usr/bin/env python3
"""dump_batch.py <chat-uuid> <out-file> — dump ALL assistant content_blocks
from the server-side batch store to a durable JSON file.

The batch store (/api/v1/chats/<id>/messages/batch) is the server-side truth:
it survives DOM collapse, renderer wedges, and tab loss. This banks a lane's
full progress so a server-side purge costs nothing (early+continuous harvest
doctrine, banked 2026-10-13).

Output JSON: {chat, dumped_at, messages: [{id, ts, role, n_blocks,
blocks: [{type, content}]}], total_chars}
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cid, out = sys.argv[1], sys.argv[2]
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        print(json.dumps({"err": "no chat.z.ai tab"}))
        return 2
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
          const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
          const r = await fetch('/api/v1/chats/%s', {credentials: 'include', cache: 'no-store', headers: hdr});
          if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
          const j = await r.json();
          const msgs = ((j.chat || {}).history || {}).messages || {};
          const byTs = Object.values(msgs).sort((a,b) => (a.timestamp||0)-(b.timestamp||0));
          const ids = byTs.map(m => m.id).filter(Boolean);
          if (!ids.length) return JSON.stringify({err: 'no ids'});
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
            if (!m) continue;
            if ((m.role || 'assistant') === 'user') continue;
            const blocks = m.content_blocks || m.blocks || [];
            out.push({id, ts: m.timestamp || m.ts || 0, role: m.role, n_blocks: blocks.length, blocks});
          }
          return JSON.stringify({out});
        })()""" % (cid, cid)
        raw = ws.eval(js, await_promise=True, timeout=60)
        d = json.loads(raw)
        if "err" in d:
            print(json.dumps(d))
            return 2
        msgs = d["out"]
        total = 0
        for m in msgs:
            for b in m["blocks"]:
                c = b.get("content")
                if isinstance(c, str):
                    total += len(c)
                elif c is not None:
                    total += len(json.dumps(c))
        doc = {
            "chat": cid,
            "dumped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_chars": total,
            "n_messages": len(msgs),
            "messages": msgs,
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(json.dumps({"ok": True, "out": out, "n_messages": len(msgs), "total_chars": total}))
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
