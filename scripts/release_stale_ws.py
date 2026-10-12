#!/usr/bin/env python3
"""release_stale_ws.py — release STALE sandbox holders via the workspaces API.

§11d doctrine: packets that land while the account's sandbox concurrency is
FULL sit queued forever. Release stale holders (DELETE
/api/v1/web-dev/workspaces/<chat-uuid>) after verifying they are not live
registry sessions. The KEEP set is passed as args (chat uuid prefixes or
session names from the registry); every active workspace whose chat is NOT
in the keep set and whose chat shows no recent update activity is released.

Usage: release_stale_ws.py <keep-chat-uuid-or-prefix> [...]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def page_eval(js, timeout=60):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def api(method, path, body=None):
    payload = json.dumps(body) if body is not None else "null"
    js = f"""
    (async () => {{
      const r = await fetch('{path}', {{
        method: '{method}',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: {payload} === null ? undefined : {payload}
      }});
      const t = await r.text();
      return r.status + ' ' + t.slice(0, 500);
    }})()
    """
    return page_eval(js)


def main():
    keeps = set(a.removeprefix("chat-") for a in sys.argv[1:])
    raw = page_eval("""
    (async () => {
      const r = await fetch('/api/v1/web-dev/workspaces/user-fc', {credentials:'include'});
      return await r.text();
    })()
    """)
    data = json.loads(raw)
    v = data.get("data", data)
    items = []
    if isinstance(v, dict):
        for k in ("workspaces", "list", "items"):
            if isinstance(v.get(k), list):
                items = v[k]
                break
    elif isinstance(v, list):
        items = v
    if not items:
        print("no active workspaces found — nothing to release")
        return
    print(f"{len(items)} active workspace(s)")
    for it in items:
        cid = str(it.get("chat_id") or it.get("chatId") or "")
        cid = cid.removeprefix("chat-")
        title = it.get("chat_title") or "?"
        updated = it.get("chat_updated_at") or 0
        keep = any(cid.startswith(k) or k.startswith(cid[:8]) for k in keeps)
        print(f"- {cid[:12]} '{title}' updated={updated} keep={keep}")
        if keep:
            print("  KEEP (live registry session)")
            continue
        print("  releasing (DELETE)...")
        print("  " + api("DELETE", f"/api/v1/web-dev/workspaces/{cid}")[:300])
    print("== post-release state:")
    print(page_eval("""
    (async () => {
      const r = await fetch('/api/v1/web-dev/workspaces/user-fc', {credentials:'include'});
      const t = await r.text();
      try { const d = JSON.parse(t); const v = d.data || d;
        const items = v.workspaces || v.list || v.items || [];
        return JSON.stringify({total: v.total ?? items.length, limit: v.limit, ids: items.map(i => (i.chat_id||'').slice(5,17)}));
      } catch (e) { return t.slice(0, 300); }
    })()
    """)[:500])


if __name__ == "__main__":
    main()
