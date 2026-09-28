#!/usr/bin/env python3
"""chat_content.py <chat-id> [role] — print the last N messages' content via the chats API.
Works with zero live tabs (the lesson-107 CDP-free law)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chats_http import api  # noqa

def main():
    chat_id = sys.argv[1]
    role_filter = sys.argv[2] if len(sys.argv) > 2 else None
    tail = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    data = api(f"/api/v1/chats/{chat_id}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or {}
    msgs = inner.get("history", {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    sel = [m for m in msgs if (not role_filter or m.get("role") == role_filter)]
    for m in sel[-tail:]:
        print(f"===== [{m.get('role')}] gen={m.get('generating')} len={len(m.get('content') or '')} =====")
        print((m.get("content") or "")[:6000])
        print()

if __name__ == "__main__":
    main()
