#!/usr/bin/env python3
"""account_activity.py — list recent chats on the logged-in z.ai account via
the browser's own credentials (CDP eval fetch, await_promise). Shows which
sessions are actively generating (recent updated timestamps) — the
account-concurrency diagnostic."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

tabs = [t for t in channel.list_tabs() if "chat.z.ai" in (t.get("url") or "")]
if not tabs:
    print("no chat tab")
    sys.exit(1)
ws = channel.CDP(tabs[-1]["webSocketDebuggerUrl"])
js = """(async () => {
  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
  const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
  const r = await fetch('/api/v1/chats/list?page=1&size=14', {credentials: 'include', cache: 'no-store', headers: hdr});
  if (!r.ok) return JSON.stringify({err: 'http-' + r.status});
  const j = await r.json();
  const items = (j.data && (j.data.list || j.data.chats)) || (j.list) || (Array.isArray(j) ? j : []);
  return JSON.stringify({n: items.length, chats: items.map(c => ({
    id: String(c.id || c.uuid || '').slice(0, 8),
    title: String(c.title || '').slice(0, 46),
    updated: c.updatedAt || c.updateTime || c.updated_at || null}))});
})()"""
try:
    raw = ws.eval(js, await_promise=True, timeout=30)
    d = json.loads(raw if isinstance(raw, str) else json.dumps(raw))
finally:
    ws.close()
if d.get("err"):
    print("probe error:", d["err"])
    sys.exit(2)
now = time.time()
print("recent chats:", d.get("n"))
for c in d.get("chats", []):
    age = "?"
    ts = c.get("updated")
    if ts:
        try:
            t = float(ts) / (1000 if float(ts) > 1e12 else 1)
            age = f"{int(now - t)}s"
        except Exception:
            age = str(ts)[:19]
    print(f"  {c['id']}  {age:>9}  {c['title']}")
