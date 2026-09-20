#!/usr/bin/env python3
"""dump_prompt.py — recover a dispatched worker prompt VERBATIM from the
server-side message tree of a chat (lesson-118 recovery rail).

The full worker-spec prompt sits as the first USER message of the chat.
This tool fetches the chat detail via the lesson-107 HTTP rail (Bearer
token from a chat.z.ai tab's localStorage — no CDP strain on worker
tabs) and writes the first user message to disk.

Usage:
  dump_prompt.py <chat-id> [out-file]
Default out-file: /home/z/prompts-recovered/<chat-id-prefix>/user-msg-0.md
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chats_http  # noqa: E402


def first_user_message(chat_id: str) -> dict:
    data = chats_http.api(f"/api/v1/chats/{chat_id}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    msgs = inner.get("history", {}).get("messages", {})
    if isinstance(msgs, dict):
        rows = list(msgs.values())
    elif isinstance(msgs, list):
        rows = msgs
    else:
        rows = []
    rows.sort(key=lambda m: m.get("createdAt") or 0)
    users = [m for m in rows if m.get("role") == "user" and isinstance(m.get("content"), str)
             and len(m.get("content") or "") > 200]
    if not users:
        # fall back to ANY user message (echo/continuations included)
        users = [m for m in rows if m.get("role") == "user"]
    if not users:
        raise RuntimeError(f"no user messages in chat {chat_id}")
    return users[0]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    chat_id = sys.argv[1]
    msg = first_user_message(chat_id)
    content = msg.get("content") or ""
    prefix = chat_id[:8]
    out = sys.argv[2] if len(sys.argv) > 2 else f"/home/z/prompts-recovered/{prefix}/user-msg-0.md"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        fh.write(content)
    print(f"chat {chat_id}: first user message ({len(content)} chars) -> {out}")
    print("--- head ---")
    print(content[:400])
    print("--- tail ---")
    print(content[-200:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
