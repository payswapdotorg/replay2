#!/usr/bin/env python3
"""check_wave_sessions.py — post-login one-shot: server-side state of the
two in-flight worker chats (PA-021b d25102e5, PA-022 838d1236).
Verdict per chat: generated (assistant content > 50 chars) / spawned-empty
(turn open, queued) / packet-only (no assistant turn) / dead (404/500).
"""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CHATS = {
    "PA-021b": "d25102e5-fcd0-43ed-bf8c-8a4a011b536e",
    "PA-022": "838d1236-fd97-465d-8680-b680668365d4",
}

JS = """(async () => {
  const t = localStorage.getItem('token') || '';
  const out = {};
  for (const [name, id] of %s) {
    try {
      const r = await fetch('/api/v1/chats/' + id, { credentials:'include',
        headers: {'Authorization': 'Bearer ' + t} });
      if (r.status !== 200) { out[name] = {status: r.status, verdict: 'dead'}; continue; }
      const j = await r.json().catch(()=>null);
      const d = (j && (j.data || j)) || {};
      const h = (d.chat && d.chat.history && d.chat.history.messages) || {};
      const vals = Object.values(h);
      const asst = vals.filter(m => m.role === 'assistant');
      const content = asst.length ? JSON.stringify(asst[asst.length-1].content || '') : '';
      let verdict = 'packet-only';
      if (asst.length && content.length > 50) verdict = 'GENERATED';
      else if (asst.length) verdict = 'spawned-empty (queued)';
      out[name] = {status: 200, msgs: vals.length, asst: asst.length,
                   contentLen: content.length, upd: d.updated_at, verdict};
    } catch (e) { out[name] = {err: String(e).slice(0,80)}; }
  }
  return JSON.stringify(out);
})()""" % json.dumps(list(CHATS.items()))


def main():
    tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
    if not tabs:
        print("NO chat.z.ai tab — login first")
        return 1
    for t in tabs:
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
            try:
                raw = c.eval(JS, timeout=30, await_promise=True)
                if raw:
                    print(raw)
                    return 0
            finally:
                c.close()
        except Exception as e:
            print("tab %s failed: %s" % (t["id"][:8], str(e)[:60]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
