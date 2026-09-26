#!/usr/bin/env python3
"""wave_status.py — one-shot compact status for the live AISE worker wave.

Per worker: chat phase (batch store) + pod tree entry count + slot map.
One line per worker + a slots line. For the Lead's resident watch loop.
"""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
from batch_probe import call  # noqa: E402

SESSIONS = {
    "post004": "ace489c2-e8ee-428f-b8fc-cc67028df914",
    "post005": "d1168f27-be9c-4625-aae8-87d6e693fd06",
}
FILES_API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"
TOK = open("/home/z/replay2/scripts/flags/chat_token").read().strip().strip('"')


def workspace_map():
    try:
        d = call("/api/v1/web-dev/workspaces/user-fc")
        out = {}
        for w in d.get("workspaces", []):
            cid = (w.get("chat_id") or "").replace("chat-", "")
            out[cid[:8]] = w.get("function_name")
        return out
    except Exception as e:
        return {"err": str(e)[:60]}


def pod_count(cid, ws):
    if not ws:
        return -1
    try:
        tree = call(f"{FILES_API}/ls-tree", None) if False else None
        import urllib.request
        body = json.dumps({"chatId": cid, "workspace_id": ws, "path": "my-project"}).encode()
        req = urllib.request.Request(f"{FILES_API}/ls-tree", data=body, method="POST")
        req.add_header("Authorization", f"Bearer {TOK}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as r:
            t = json.loads(r.read())
        entries = t if isinstance(t, list) else (t.get("data") or t.get("tree") or [])
        return len(entries) if isinstance(entries, list) else -1
    except Exception:
        return -2


def chat_state(cid):
    try:
        chat = call(f"/api/v1/chats/{cid}")
        c = chat.get("chat") or chat
        msgs = (c.get("history") or {}).get("messages") or {}
        vals = msgs.values() if isinstance(msgs, dict) else msgs
        ids = [m.get("id") for m in vals if m.get("id")]
        batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}, timeout=60)
        data = (batch.get("data") or batch.get("messages")) or {}
        best, done, filled = 0, False, False
        import re
        h40 = re.compile(r"\b[0-9a-f]{40}\b")
        ph = re.compile(r"<[A-Za-z0-9_ -]{4,40}>")
        for m in data.values():
            if not m or (m.get("role") or "assistant") != "assistant":
                continue
            w = json.dumps(m)
            if len(w) > best:
                best = len(w)
            if m.get("done") is True:
                done = True
            i = w.find("COMPLETION REPORT")
            if i >= 0:
                win = w[i:i + 900]
                if h40.search(win) and not ph.search(win):
                    filled = True
        return best, done, filled
    except Exception as e:
        return -1, False, f"err:{type(e).__name__}"


def main():
    import time
    print(time.strftime("[%H:%M:%S]"), "wave status:")
    wsmap = workspace_map()
    used = len(wsmap) if "err" not in wsmap else "?"
    print(f"  slots: {used}/3")
    for name, cid in SESSIONS.items():
        chars, done, filled = chat_state(cid)
        ws = wsmap.get(cid[:8], "")
        n = pod_count(cid, ws)
        print(f"  {name}: chars={chars} done={done} filled={filled} pod_files={n}")


if __name__ == "__main__":
    main()
