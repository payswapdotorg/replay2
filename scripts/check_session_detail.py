#!/usr/bin/env python3
"""check_session_detail.py — deep-inspect one chat session's server-side
message tree: full assistant message JSON (all content shapes: text parts,
thinking, tool calls) so an 'empty' verdict is byte-evidenced, not assumed.
"""
import json
import sys

sys.path.insert(0, '/home/z/replay2/scripts')
import channel


def page_eval(js, timeout=45):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def main():
    cid = sys.argv[1]
    js = f"""
    (async () => {{
      // 2026-09-11 fix: Bearer token required — cookie-only auth returns an
      // EMPTY message tree (false '0 messages' verdicts). localStorage 'token'
      // is a raw JWT string.
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include', headers: {{'Authorization': 'Bearer ' + t}}}});
      const t2 = await r.text();
      return t2.slice(0, 400000);
    }})()
    """
    raw = page_eval(js, timeout=60)
    try:
        d = json.loads(raw)
    except Exception:
        print("RAW (first 3000):", raw[:3000])
        return 1

    hist = (d.get("chat") or {}).get("history") or {}
    mmap = hist.get("messages") or {}
    msgs = list(mmap.values())
    print(f"chat {cid}: {len(msgs)} messages in tree")
    for m in msgs:
        role = m.get("role")
        content = m.get("content")
        shapes = {}
        if isinstance(content, str):
            shapes["str_len"] = len(content)
            preview = content[:200].replace("\n", " | ")
        elif isinstance(content, list):
            shapes["parts"] = []
            for p in content:
                if isinstance(p, dict):
                    kinds = {k: (len(v) if isinstance(v, str) else str(v)[:40])
                             for k, v in p.items() if k in ("type", "text", "thinking", "id", "name")}
                    shapes["parts"].append(kinds)
            texts = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
            preview = texts[:200].replace("\n", " | ")
        else:
            shapes["type"] = str(type(content))
            preview = str(content)[:200]
        print(f"  [{role}] shapes={json.dumps(shapes)[:300]}")
        print(f"    preview: {preview[:200]}")
        kids = m.get("childrenIds") or []
        ts = m.get("timestamp")
        print(f"    ts={ts} children={len(kids)} model={m.get('model','')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
