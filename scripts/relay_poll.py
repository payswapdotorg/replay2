#!/usr/bin/env python3
"""relay_poll.py — poll the workspaces files API for each lane's RELAY-MANIFEST.txt.
Zero-tab completion detection (the SPA outage law): the relay at the storage
root is the worker's completion beacon."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import urllib.request

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags")
API = "https://chat.z.ai/api/v1/web-dev/workspaces/files"
TOK = open(os.path.join(FLAGS, "chat_token")).read().strip().strip('"')

def api(payload):
    req = urllib.request.Request(API + "/content", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {TOK}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        return b"" if e.code == 404 else f"ERR:{e}".encode()
    except Exception as e:
        return f"ERR:{e}".encode()

def ws_list():
    url = "https://chat.z.ai/api/v1/web-dev/workspaces/user-fc"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOK}"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r).get("workspaces", [])

def probe(path, chat, ws):
    raw = api({"op": "content", "chatId": chat, "workspace_id": ws, "rev": "latest", "filepath": path})
    return raw if not raw.startswith(b"ERR") else None

def main():
    # map registry name->chat
    reg = {}
    for line in open(os.path.join(FLAGS, "session_registry.jsonl")):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("url") and "/c/" in (d.get("url") or ""):
            reg[d["name"]] = d["url"].split("/c/")[1].split("/")[0].split("?")[0]
    chats = {}
    for w in ws_list():
        cid = (w.get("chat_id") or "").replace("chat-", "")
        if len(cid) >= 30:
            chats[cid[:8]] = (cid, w.get("function_name"))
    for name in sorted(set(reg)):
        chat = reg[name]
        hit = chats.get(chat[:8])
        if not hit:
            print(f"{name}: no workspace for chat {chat[:8]}")
            continue
        cid, ws = hit
        m = probe("RELAY-MANIFEST.txt", cid, ws)
        print(f"{name}: chat={chat[:8]} ws={ws[:14]} relay={'PRESENT' if m else 'absent'}")
        if m:
            print(m.decode()[:400])

if __name__ == "__main__":
    main()
