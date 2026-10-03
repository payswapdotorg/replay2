#!/usr/bin/env python3
"""Forensic extraction of the W140 chat transcript (server-side batch store).
Returns: completion-report window, tail, and search hits for off-scope markers."""
import json
import sys

sys.path.insert(0, '/home/z/replay2/scripts')
import channel

CID = '910895e1-62b1-4f97-b270-b4f85d95909f'
MARKER = 'W140 COMPLETION REPORT'
NEEDLES = ['ADR-0002', 'Predictive Twin', 'issue #3', 'Wave 14', 'wave 14',
           'wave14', 'predictive twin', '49c277a', '6afb1e8', 'integration/wave0',
           'git push origin main', 'push origin main', 'W150', 'W151', 'W152', 'W153']

js = """(async () => {
  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
  const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
  const r = await fetch('/api/v1/chats/%s', {credentials: 'include', cache: 'no-store', headers: hdr});
  const j = await r.json();
  const msgs = ((j.chat || {}).history || {}).messages || {};
  const byTs = Object.values(msgs).sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
  const ids = byTs.map(m => m.id).filter(Boolean);
  const br = await fetch('/api/v1/chats/%s/messages/batch', {
    credentials: 'include', cache: 'no-store', method: 'POST',
    headers: Object.assign({'Content-Type': 'application/json'}, hdr),
    body: JSON.stringify({ids})});
  const bj = await br.json();
  const data = (bj && (bj.data || bj.messages)) || {};
  let parts = [];
  for (const id of Object.keys(data)) {
    const m = data[id];
    if (!m || m.role === 'user') continue;
    const blocks = m.content_blocks || [];
    let txt = '';
    for (const b of blocks) {
      if (typeof b === 'string') txt += b;
      else if (b && typeof b.text === 'string') txt += b.text;
      else if (b && typeof b.content === 'string') txt += b.content;
    }
    if (!txt && typeof m.content === 'string') txt = m.content;
    if (txt) parts.push(txt);
  }
  const full = parts.join('\\n');
  const res = {total: full.length, parts: parts.length};
  const mi = full.indexOf(%s);
  if (mi >= 0) res.report = full.slice(mi, mi + 7000);
  res.tail = full.slice(-3500);
  res.hits = {};
  const needles = %s;
  for (const n of needles) {
    let c = 0, i = -1, first = -1;
    while ((i = full.indexOf(n, i + 1)) >= 0) { c++; if (first < 0) first = i; }
    if (c) res.hits[n] = {count: c, at: first};
  }
  return JSON.stringify(res);
})()""" % (CID, CID, json.dumps(MARKER), json.dumps(NEEDLES))

tabs = [t for t in channel.list_tabs() if 'chat.z.ai' in (t.get('url') or '')]
ws = channel.CDP(tabs[-1]['webSocketDebuggerUrl'])
try:
    r = ws.call('Runtime.evaluate', {'expression': js, 'awaitPromise': True,
                                     'returnByValue': True}, timeout=180)
    v = json.loads(r.get('result', {}).get('value') or '{}')
finally:
    try:
        ws.close()
    except Exception:
        pass

print('total transcript chars:', v.get('total'), '| parts:', v.get('parts'))
print('\n=== NEEDLE HITS (forensics: did the worker do off-scope Wave-14 work?) ===')
for n, h in sorted((v.get('hits') or {}).items(), key=lambda kv: kv[1]['at']):
    print(f"  {n!r}: {h['count']}x first@{h['at']}")
print('\n=== TAIL (last 3500 chars) ===')
print(v.get('tail', ''))
print('\n=== REPORT WINDOW (marker +7000) ===')
print(v.get('report', 'MARKER NOT FOUND'))
