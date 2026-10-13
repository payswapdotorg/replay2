#!/usr/bin/env python3
"""phantom_tab_gc.py — close TRUE-phantom chat tabs during capacity assaults.

Problem (observed 2026-10-13 w9c re-dispatch): every failed assault round
during a GLM-5.3 capacity peak leaves behind a chat tab whose send never
landed — the chat shell exists briefly or not at all server-side. Tabs pile
up ~100MB each and starve the box (the frame core died of this once).

Safety law: a tab is ONLY closed when BOTH hold:
  (a) its /c/<id> chat id has NO live registry row (no sent=true row that
      is not later voided/failed/done for a name whose tab matches), and
  (b) the chat id is ABSENT from the server-side chats list (verified over
      HTTP with the cached token) — meaning the send DEFINITELY never
      landed. A chat that exists server-side is never touched (it may be a
      live worker or a chat the operator wants).
Runs every 120s; logs to logs/phantom_tab_gc.log. DFork-launched; exits
cleanly if the browser is gone.
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(BASE, "flags", "session_registry.jsonl")
LOG = os.path.join(BASE, "logs", "phantom_tab_gc.log")
CDP = "http://127.0.0.1:9222"
INTERVAL = 120


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def live_chat_ids_from_registry():
    """chat ids that have a live (sent, not invalidated) registry row."""
    try:
        rows = [json.loads(l) for l in open(REG).read().split("\n") if l.strip()]
    except Exception:
        return set()
    # later invalidation rows void earlier creates per name
    state = {}
    for r in rows:
        name = r.get("name")
        if not name:
            continue
        if r.get("action") in ("void", "voided", "failed", "done"):
            state[name] = None
        elif r.get("sent") and r.get("url"):
            state[name] = r.get("url")
    keep = set()
    for name, url in state.items():
        if url and "/c/" in url:
            keep.add(url.split("/c/")[1][:36])
    return keep


def server_chat_ids():
    ids = None  # None = tooling failure (touch nothing)
    try:
        sys.path.insert(0, BASE)
        import chats_http
        tok = chats_http.get_token().strip().strip('"')
        req = urllib.request.Request(
            "https://chat.z.ai/api/v1/chats/list?limit=100",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = items.get("items", [])
        ids = {(it.get("id") or "") for it in items}
    except Exception as e:
        log(f"server list tooling failure: {str(e)[:60]} — touching nothing")
    return ids


def cdp_tabs():
    try:
        return json.load(urllib.request.urlopen(CDP + "/json/list", timeout=10))
    except Exception:
        return []


def close_tab(tid):
    try:
        urllib.request.urlopen(
            urllib.request.Request(CDP + "/json/close/" + tid, method="PUT"), timeout=10
        )
        return True
    except Exception:
        return False


def main():
    log("phantom_tab_gc armed (120s rounds, TRUE-phantom-only law)")
    while True:
        try:
            tabs = [t for t in cdp_tabs() if t.get("type") == "page"]
            in_chat = [t for t in tabs if "chat.z.ai/c/" in (t.get("url") or "")]
            if not in_chat:
                time.sleep(INTERVAL)
                continue
            keep = live_chat_ids_from_registry()
            server = server_chat_ids()
            closed = 0
            for t in in_chat:
                cid = (t.get("url") or "").split("/c/")[1][:36]
                if cid in keep:
                    continue  # registry says this chat is live — never touch
                if server is None or cid in server:
                    continue  # exists server-side or unknown — never touch
                if close_tab(t["id"]):
                    closed += 1
                    log(f"closed TRUE phantom {t['id'][:10]} chat {cid[:8]} (absent server-side, no registry row)")
            if closed:
                log(f"round: closed {closed} phantom tab(s), {len(in_chat)} in-chat seen")
        except Exception as e:
            log(f"round error: {str(e)[:80]}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
