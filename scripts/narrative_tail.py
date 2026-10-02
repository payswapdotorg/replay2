#!/usr/bin/env python3
"""narrative_tail.py <chat-uuid> [min_blocks] [n_chars] — extract the tail text blocks of the last work-rich assistant batch."""
import sys, json
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

cid = sys.argv[1]
min_blocks = int(sys.argv[2]) if len(sys.argv) > 2 else 20
nchars = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
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
  const rich = [];
  for (const id of Object.keys(data)) {
    const m = data[id];
    if (!m || (m.role || 'assistant') === 'user') continue;
    const blocks = m.content_blocks || m.blocks || [];
    if (blocks.length >= %d) rich.push({ts: m.timestamp || 0, blocks});
  }
  rich.sort((a,b) => a.ts - b.ts);
  if (!rich.length) return JSON.stringify({err: 'no rich batches'});
  const last = rich[rich.length - 1];
  const texts = [];
  let toolCalls = [];
  for (const b of last.blocks) {
    if (b && b.type === 'text' && typeof b.content === 'string' && b.content.trim()) texts.push(b.content);
    if (b && (b.type === 'tool_call' || b.type === 'tool_use')) toolCalls.push((b.name || '') + ':' + String(b.content || '').slice(0, 200));
  }
  return JSON.stringify({ts: last.ts, nBlocks: last.blocks.length, nTexts: texts.length,
    tail: texts.slice(-4).join('\\n\\n[...]\\n\\n').slice(-%d), lastTools: toolCalls.slice(-5)});
})()""" % (cid, cid, min_blocks, nchars)
raw = ws.eval(js, await_promise=True, timeout=60)
d = json.loads(raw)
if "err" in d:
    print(json.dumps(d)); sys.exit(2)
print("batch ts:", d["ts"], "nBlocks:", d["nBlocks"], "nTexts:", d["nTexts"])
for t in d.get("lastTools", []):
    print("TOOL:", t)
print("--- narrative tail ---")
print(d.get("tail", ""))
