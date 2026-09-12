#!/usr/bin/env python3
"""api_watch.py — poll the chat detail API for message-tree progress.

Complements queue_watch (DOM-based): works even when the chat page won't
render (rationing throttles the SPA's fetches). Navigates a dedicated tab
to /api/v1/chats/<id> and logs message count + latest timestamps + title.

Usage: api_watch.py <chat-id> [interval-sec]
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/my-project/replay2/scripts")
from channel import CDP, list_tabs

LOG = "/tmp/api_watch.log"


def poll(chat_id):
    tabs = list_tabs()
    # reuse a tab already on the API URL, else pick any chat.z.ai tab
    t = next((x for x in tabs if "api/v1/chats" in (x.get("url") or "")), None)
    if not t:
        return None, "no-api-tab"
    cdp = CDP(t["webSocketDebuggerUrl"], timeout=45)
    url = f"https://chat.z.ai/api/v1/chats/{chat_id}"
    try:
        cdp.call("Page.navigate", {"url": url}, timeout=20)
    except Exception:
        pass  # response frame often lost; navigation still lands
    for _ in range(6):
        time.sleep(4)
        try:
            body = cdp.eval("(document.body.innerText || '')", timeout=15)
            d = json.loads(body)
            msgs = d.get("chat", {}).get("history", {}).get("messages", {})
            items = sorted(msgs.values(), key=lambda m: m.get("timestamp", 0))
            last = items[-1] if items else {}
            return {
                "n": len(items),
                "last_ts": last.get("timestamp"),
                "last_role": last.get("role"),
                "last_id": (last.get("id") or "")[:8],
                "title": d.get("title", ""),
            }, None
        except Exception:
            continue
    return None, "parse-fail"


def main():
    chat_id = sys.argv[1]
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    seen_last = None
    while True:
        snap, err = poll(chat_id)
        stamp = time.strftime("%H:%M:%S")
        if err:
            line = f"[{stamp}] err={err}"
        else:
            line = (f"[{stamp}] msgs={snap['n']} last={snap['last_role']}"
                    f"@{snap['last_ts']} ({snap['last_id']})")
        with open(LOG, "a") as f:
            f.write(line + "\n")
        print(line, flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
