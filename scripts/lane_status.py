#!/usr/bin/env python3
"""lane_status.py — batch-store status for all wave lanes from a dedicated tab.

Prints per lane: tree totals, per-assistant-message block stats (nBlocks,
serialized len, block kinds), tool-call names found, and the last text
snippet. The batch store is the server-side truth (§11a).
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

LANES = {
    "w125": "b55f0e57-e538-4eac-8d43-cd9013d4634a",
    "w126": "cfdefe55-eee0-4a65-8258-9dbf8d4d355d",
    "w131": "734cbc9a-6d9d-4499-ad67-cc854246eb98",
}


def probe(cid):
    tab = channel.new_tab("https://chat.z.ai/")
    if tab is None:
        return {"err": "tab"}
    time.sleep(5)
    tabs = {t["id"]: t for t in channel.list_tabs()}
    t = tabs.get(tab["id"], tab)
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=60)
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
          const per = [];
          for (const id of Object.keys(data)) {
            const m = data[id];
            if (!m) continue;
            const blocks = m.content_blocks || m.blocks || [];
            const kinds = {};
            const tools = [];
            let lastText = '';
            for (const b of blocks) {
              const k = b.type || (b.function ? 'tool_call' : '?');
              kinds[k] = (kinds[k] || 0) + 1;
              if (b.function) tools.push(b.function.name || '?');
              if (b.type === 'text' && b.text) lastText = b.text;
            }
            per.push({role: m.role || '?', len: JSON.stringify(m).length, nBlocks: blocks.length,
                      kinds, tools: tools.slice(0, 12), lastText: String(lastText).slice(-160)});
          }
          return JSON.stringify({totalMsgs: ids.length, per});
        })()""" % (cid, cid)
        return json.loads(ws.eval(js, await_promise=True, timeout=90))
    finally:
        try:
            ws.close()
        except Exception:
            pass
        try:
            channel._http_json("/json/close/" + t["id"], method="PUT")
        except Exception:
            pass


if __name__ == "__main__":
    only = sys.argv[1:] or list(LANES)
    for name in only:
        cid = LANES.get(name, name)
        try:
            d = probe(cid)
        except Exception as e:
            d = {"err": str(e)[:120]}
        print(f"===== {name} ({cid[:8]}) =====")
        if "err" in d:
            print("  ERR:", d["err"])
            continue
        print(f"  tree msgs: {d.get('totalMsgs')}")
        for p in d.get("per", []):
            tools = ",".join(p.get("tools") or []) or "-"
            print(f"  [{p['role']}] len={p['len']} blocks={p['nBlocks']} kinds={p.get('kinds')} tools={tools}")
            if p.get("lastText"):
                print(f"      tail: {p['lastText'][:150]}")
