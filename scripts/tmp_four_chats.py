#!/usr/bin/env python3
"""One-off: summarize the four active DEP chats (roles, sizes, last activity)."""
import json, sys, time
sys.path.insert(0, '/home/z/replay2/scripts')
import channel

CHATS = {
    "dep-001": "ec33a313-1c40-4c87-abe9-a69c2a7c34d8",
    "dep-010-r2": "5c355d3c-1aaa-40f0-826c-27207e0c81c4",
    "dep-020": "c312fed9-0df8-4a2c-bea6-716ac8880c80",
    "dep-010-r1?": "7dc0dbfc-3a3c-4db2-9f2c-215c5ebb1416",
}

def _eval_fresh(js, timeout=55):
    """Wedge-proof: eval on a fresh chat.z.ai tab, then close it (dep_land pattern)."""
    t = channel.new_tab("https://chat.z.ai/")
    try:
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=25)
        for _ in range(20):
            try:
                href = c.eval("location.href", await_promise=False, timeout=8)
                if href and "chat.z.ai" in href and c.eval(
                        "document.readyState", await_promise=False, timeout=8) in ("interactive", "complete"):
                    break
            except Exception:
                pass
            time.sleep(1.5)
        return c.eval(js, await_promise=True, timeout=timeout)
    finally:
        try:
            channel.CDP(t["webSocketDebuggerUrl"], timeout=10).call(
                "Target.closeTarget", {"targetId": t.get("id")}, timeout=8)
        except Exception:
            pass

ids_json = json.dumps(list(CHATS.values()))
js = """
(async () => {
  const out = {};
  for (const cid of %s) {
    try {
      const r = await fetch('/api/v1/chats/' + cid, {credentials: 'include'});
      if (r.status !== 200) { out[cid] = {status: r.status}; continue; }
      const j = await r.json();
      const d = j.data || j;
      const msgs = (d.chat && d.chat.history && d.chat.history.messages) || {};
      const arr = Object.values(msgs);
      let lastUser = 0, lastAssist = 0, assistLen = 0, userLen = 0, nUser = 0, nAssist = 0, lastTs = 0;
      for (const m of arr) {
        const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content || '');
        if (m.role === 'user') { nUser++; userLen += c.length; if (m.timestamp > lastUser) lastUser = m.timestamp; }
        else if (m.role === 'assistant') { nAssist++; assistLen += c.length; if (m.timestamp > lastAssist) lastAssist = m.timestamp; }
        if (m.timestamp > lastTs) lastTs = m.timestamp;
      }
      out[cid] = {status: 200, title: (d.title || '').slice(0, 40), nUser, nAssist,
                  userLen, assistLen, lastUserTs: lastUser, lastAssistTs: lastAssist,
                  updated: d.updated_at, created: d.created_at};
    } catch (e) { out[cid] = {err: String(e).slice(0, 80)}; }
  }
  return JSON.stringify(out);
})()
""" % ids_json

raw = _eval_fresh(js, timeout=55000)
data = json.loads(raw) if isinstance(raw, str) else raw
now = time.time()
for name, cid in CHATS.items():
    d = data.get(cid, {})
    if d.get('status') != 200:
        print(f"{name:12s} {cid[:8]}  -> {json.dumps(d)[:120]}")
        continue
    age_a = int(now - d['lastAssistTs']) if d['lastAssistTs'] else -1
    print(f"{name:12s} {cid[:8]}  title={d['title']!r} user={d['nUser']}({d['userLen']}ch) "
          f"assist={d['nAssist']}({d['assistLen']}ch) lastAssistAge={age_a}s updated={d['updated']}")
