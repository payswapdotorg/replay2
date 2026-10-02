#!/usr/bin/env python3
"""batch_tail.py <chat-uuid> [n_blocks] — read the batch store assistant content_blocks, print tail."""
import sys, time, json
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

cid = sys.argv[1]
nblk = int(sys.argv[2]) if len(sys.argv) > 2 else 6
tab = channel.find_tab("chat.z.ai")
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
      let best = null, bestLen = -1;
      for (const id of Object.keys(data)) {
        const m = data[id];
        if (!m || (m.role || 'assistant') === 'user') continue;
        const L = JSON.stringify(m).length;
        if (L > bestLen) { bestLen = L; best = m; }
      }
      if (!best) return JSON.stringify({err: 'no assistant blocks'});
      const blocks = best.content_blocks || best.blocks || [];
      return JSON.stringify({totalLen: bestLen, nBlocks: blocks.length, tail: blocks.slice(-%d)});
    })()""" % (cid, cid, nblk)
    raw = ws.eval(js, await_promise=True, timeout=60)
    d = json.loads(raw)
    if "err" in d:
        print(json.dumps(d)); sys.exit(2)
    print("totalLen:", d["totalLen"], "nBlocks:", d["nBlocks"])
    for b in d["tail"]:
        t = b.get("type", "?")
        txt = ""
        if isinstance(b.get("content"), str):
            txt = b["content"]
        elif isinstance(b.get("content"), dict):
            txt = json.dumps(b["content"])
        elif isinstance(b.get("text"), str):
            txt = b["text"]
        txt = txt.replace("\n", " ⏎ ")
        print(f"--[{t}] {txt[:400]}")
finally:
    ws.close()
