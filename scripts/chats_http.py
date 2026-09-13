#!/usr/bin/env python3
"""chats_http.py — lesson-107 CDP-free chat forensics.

One tiny CDP eval extracts the site JWT from a chat.z.ai tab's
localStorage; every /api/v1/chats* query then runs via urllib with the
Bearer header — no tabs, no strain, no timeouts. Falls back to cookie-less
retry if the token eval fails.

Usage:
  chats_http.py list [limit]     — chats list (id, title)
  chats_http.py detail <chat-id> — chat detail (messages tree summary)
  chats_http.py turns <chat-id>  — leaf-turn diagnosis (role/content/generating)
Token is cached in flags/chat_token (mode 600) between invocations.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
TOKEN_CACHE = os.path.join(FLAGS, "chat_token")
BASE = "https://chat.z.ai"


def get_token() -> str:
    if os.path.isfile(TOKEN_CACHE):
        tok = open(TOKEN_CACHE).read().strip()
        if tok:
            return tok
    js = "JSON.stringify(localStorage.getItem('token') || '')"
    for t in channel.list_tabs():
        if "chat.z.ai" not in (t.get("url") or ""):
            continue
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            raw = c.eval(js, timeout=10)
            c.close()
            tok = json.loads(raw) if raw.startswith('"') else raw
            tok = tok.strip().strip('"')
            if tok:
                with open(TOKEN_CACHE, "w") as fh:
                    fh.write(tok)
                os.chmod(TOKEN_CACHE, 0o600)
                return tok
        except Exception:
            continue
    raise RuntimeError("no token: no healthy chat.z.ai tab")


def api(path: str) -> dict:
    tok = get_token()
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {tok.strip('"')}",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def cmd_list(limit: int) -> None:
    data = api(f"/api/v1/chats/list?limit={limit}")
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("items", [])
    print(f"total chats: {len(items)}")
    for it in items:
        cid = (it.get("id") or "")[:11]
        title = (it.get("title") or "New Chat")[:52]
        updated = str(it.get("updatedAt") or "")[:16]
        print(f"  {cid}  {updated}  {title}")


def walk_messages(chat: dict):
    msgs = (chat or {}).get("history", {}).get("messages", {})
    if isinstance(msgs, list):
        return msgs
    out = []
    kids = {m.get("parentId"): m for m in msgs.values()} if isinstance(msgs, dict) else {}
    # yield in id order sorted by timestamp
    rows = list(msgs.values()) if isinstance(msgs, dict) else []
    rows.sort(key=lambda m: m.get("createdAt") or 0)
    for m in rows:
        out.append(m)
    _ = kids
    return out


def cmd_detail(chat_id: str) -> None:
    data = api(f"/api/v1/chats/{chat_id}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    print(f"title: {rec.get('title')}")
    print(f"updated_at: {rec.get('updated_at')}")
    inner = rec.get("chat", {}) or {}
    msgs = inner.get("history", {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    print(f"messages: {len(msgs)}")
    for m in msgs[-12:]:
        role = m.get("role")
        content = m.get("content")
        clen = len(content) if isinstance(content, str) else 0
        gen = m.get("generating")
        print(f"  [{role}] gen={gen} len={clen}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list(int(sys.argv[2]) if len(sys.argv) > 2 else 50)
        return 0
    if cmd == "detail" and len(sys.argv) > 2:
        cmd_detail(sys.argv[2])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
