#!/usr/bin/env python3
"""all_batch_lens.py <chat-uuid> [work-item-id] — per-message assistant batch lens/nBlocks (BATCH-MASK LAW) + report-marker scan.

2026-10-13 FIX (replay-#10, Lead diagnosis): the report scan previously
hardcoded the PPR-023 marker, so every OTHER lane's chat scanned as
"REPORT: no" — a false negative that sent the PCR-001 lane diagnosis down
a wrong path for two context cycles (the replay had in fact completed and
delivered PR #176). The marker is now a parameter:
  - explicit: all_batch_lens.py <chat-uuid> PCR-001
    -> scans "=== PCR-001 COMPLETION REPORT ===" (English) and the
       bilingual worker variant "=== PCR-001 完成报告 ===" (WO-010 lesson:
       GLM workers answer in Chinese ~half the time).
  - omitted: auto-detect EVERY "=== <ID> COMPLETION REPORT ===" /
    "=== <ID> 完成报告 ===" marker in any assistant block and list them
    all with timestamps, so no lane can be silently mis-read again.
The tailText is now taken from the CHRONOLOGICALLY LAST assistant text
block (Object.keys(data) iteration order is the batch-response order, not
time order — the old tail could show a mid-conversation block).
"""
import sys, json, time
sys.path.insert(0, "/home/z/replay2/scripts")
import channel

cid = sys.argv[1]
want = sys.argv[2].upper() if len(sys.argv) > 2 else None
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
  const out = {batches: [], totalChars: 0, totalBlocks: 0, reports: [], lastTexts: []};
  const rows = [];
  for (const id of Object.keys(data)) {
    const m = data[id];
    if (!m || (m.role || 'assistant') === 'user') continue;
    const L = JSON.stringify(m).length;
    const blocks = m.content_blocks || m.blocks || [];
    out.batches.push({len: L, nBlocks: blocks.length, ts: m.timestamp || m.created_at || null});
    out.totalChars += L; out.totalBlocks += blocks.length;
    for (const b of blocks) {
      if (b && b.type === 'text' && typeof b.content === 'string') {
        rows.push({ts: m.timestamp || 0, content: b.content});
      }
    }
  }
  rows.sort((a,b) => (a.ts||0)-(b.ts||0));
  // every completion-report marker in the conversation (auto-detect)
  const seen = {};
  for (const row of rows) {
    const found = row.content.match(/===\\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\\s*(?:COMPLETION REPORT|完成 REPORT|完成报告)\\s*===/g) || [];
    for (const f of found) {
      const idm = f.match(/===\\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)/);
      const key = idm ? idm[1] : f;
      if (!seen[key]) seen[key] = [];
      seen[key].push({ts: row.ts, afterMarker: row.content.slice(row.content.indexOf(f)).length});
    }
  }
  out.reports = Object.keys(seen).map(k => ({id: k, n: seen[k].length, firstTs: seen[k][0].ts, lastTs: seen[k][seen[k].length-1].ts, lastAfterMarker: seen[k][seen[k].length-1].afterMarker}));
  out.lastTexts = rows.slice(-2).map(r => ({ts: r.ts, tail: r.content.slice(-700)}));
  out.batches.sort((a,b) => (a.ts||0)-(b.ts||0));
  return JSON.stringify(out);
})()""" % (cid, cid)
raw = ws.eval(js, await_promise=True, timeout=60)
d = json.loads(raw)
if "err" in d:
    print(json.dumps(d)); sys.exit(2)
print("totalChars:", d["totalChars"], "totalBlocks:", d["totalBlocks"], "nBatches:", len(d["batches"]))
print("batches:", json.dumps(d["batches"]))
if want:
    hits = [r for r in d["reports"] if r["id"] == want]
    print("REPORT[%s]:" % want, "YES" if hits else "no")
    if hits:
        h = hits[0]
        print("  occurrences: %d, last at %s, chars-after-last-marker: %d" % (
            h["n"], time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(h["lastTs"])), h["lastAfterMarker"]))
else:
    print("REPORT markers (auto-detect):", json.dumps(d["reports"]) if d["reports"] else "NONE")
print("--- last 2 assistant text blocks (chronological, tails) ---")
for t in d.get("lastTexts", []):
    print("== ts", time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(t["ts"])), "==")
    print(t["tail"])
