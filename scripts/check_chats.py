#!/usr/bin/env python3
"""check_chats.py — server-side state of worker chats via in-page API.

Usage: check_chats.py [chat-id-prefix ...]   (no args = list recent chats)
Prints JSON summary of each chat's latest messages.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def page_eval(js, await_promise=True, timeout=45):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=await_promise, timeout=timeout)
    finally:
        ws.close()


def chats_list():
    js = """
    (async () => {
      const r = await fetch('/api/v1/chats/list', {credentials:'include'});
      const j = await r.json();
      return JSON.stringify(j);
    })()
    """
    return json.loads(page_eval(js))


def chat_detail(cid):
    js = f"""
    (async () => {{
      const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include'}});
      const t = await r.text();
      return t.slice(0, 200000);
    }})()
    """
    raw = page_eval(js)
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:4000]}


def main():
    args = sys.argv[1:]
    data = chats_list()
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        for k in ("chatList", "chats", "items", "list"):
            if k in items and isinstance(items[k], list):
                items = items[k]
                break
    if not isinstance(items, list):
        print("UNEXPECTED LIST SHAPE:", json.dumps(data)[:800])
        return
    print(f"total chats: {len(items)}")
    want = set(a[:8].lower() for a in args)
    rows = []
    for c in items:
        cid = str(c.get("id") or c.get("chatId") or c.get("uuid") or "")
        title = str(c.get("title") or c.get("name") or "")[:60]
        upd = c.get("updatedAt") or c.get("updateTime") or c.get("lastMessageAt") or 0
        rows.append((str(upd), cid, title, c))
    rows.sort(reverse=True)
    if not want:
        for upd, cid, title, c in rows[:25]:
            print(f"  {cid[:12]}  {upd}  {title}")
        return
    for upd, cid, title, c in rows:
        if any(cid.lower().startswith(w) for w in want):
            print(f"=== {cid} ({title}) updated={upd}")
            d = chat_detail(cid)
            msgs = d
            msgs = []
            if isinstance(d, dict):
                hist = (d.get("chat") or {}).get("history") or {}
                mmap = hist.get("messages")
                if isinstance(mmap, dict):
                    roots = [m for m in mmap.values() if not m.get("parentId")]
                    chain = []
                    cur = roots[0] if roots else None
                    while cur:
                        chain.append(cur)
                        kids = cur.get("childrenIds") or []
                        cur = mmap.get(kids[-1]) if kids else None
                    msgs = chain
            if isinstance(msgs, list) and msgs:
                import datetime as _dt
                print(f"  messages: {len(msgs)}")
                for m in msgs[-8:]:
                    role = m.get("role") or "?"
                    ts = m.get("timestamp") or 0
                    when = _dt.datetime.fromtimestamp(int(ts)).strftime("%m-%d %H:%M") if ts else "?"
                    content = m.get("content")
                    if isinstance(content, list):
                        content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
                    txt = str(content or "")[:260].replace("\n", " | ")
                    print(f"   {when} [{role}] {txt}")
            else:
                print("  detail shape:", json.dumps(d)[:600])


if __name__ == "__main__":
    main()
