#!/usr/bin/env python3
"""all_batch_lens.py <chat-uuid> — per-message assistant batch lens/nBlocks (BATCH-MASK LAW) + report-marker scan."""
import sys, json
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

cid = sys.argv[1]
tab = channel.find_tab("chat.z.ai")
ws = channel.CDP(tab["webSocketDebuggerUrl"])
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
  const out = {batches: [], totalChars: 0, totalBlocks: 0, report: null};
  let tailText = '';
  for (const id of Object.keys(data)) {
    const m = data[id];
    if (!m || (m.role || 'assistant') === 'user') continue;
    const L = JSON.stringify(m).length;
    const blocks = m.content_blocks || m.blocks || [];
    out.batches.push({len: L, nBlocks: blocks.length, ts: m.timestamp || m.created_at || null});
    out.totalChars += L; out.totalBlocks += blocks.length;
    for (const b of blocks) {
      if (b && b.type === 'text' && typeof b.content === 'string') {
        tailText = b.content;
        const idx = b.content.indexOf('=== PPR-023 COMPLETION REPORT ===');
        if (idx >= 0 && b.content.slice(idx).length > 600) {
          out.report = {len: b.content.length, afterMarker: b.content.slice(idx).length, excerpt: b.content.slice(idx, idx + 1500)};
        }
      }
    }
  }
  out.batches.sort((a,b) => (a.ts||0)-(b.ts||0));
  out.tailText = tailText ? tailText.slice(-1200) : '';
  return JSON.stringify(out);
})()""" % (cid, cid)
raw = ws.eval(js, await_promise=True, timeout=60)
d = json.loads(raw)
if "err" in d:
    print(json.dumps(d)); sys.exit(2)
print("totalChars:", d["totalChars"], "totalBlocks:", d["totalBlocks"], "nBatches:", len(d["batches"]))
print("batches:", json.dumps(d["batches"]))
print("REPORT:", "YES" if d.get("report") else "no")
if d.get("report"):
    print(d["report"]["excerpt"])
print("--- tailText (last 1200 chars of last text block) ---")
print(d.get("tailText", ""))
