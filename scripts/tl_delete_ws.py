#!/usr/bin/env python3
"""tl_delete_ws.py <chat_id>... — delete stale workspaces via in-page API.
chat_id may come with or without the chat- prefix (both forms tried)."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel


def page_eval(js, timeout=90):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def api_delete(path):
    js = f"""
    (async () => {{
      const r = await fetch('{path}', {{method: 'DELETE', credentials: 'include'}});
      const t = await r.text();
      return r.status + ' ' + t.slice(0, 300);
    }})()
    """
    return page_eval(js)


def main():
    if len(sys.argv) < 2:
        print("usage: tl_delete_ws.py <chat_id>...")
        return 2
    for raw in sys.argv[1:]:
        cid = raw.removeprefix("chat-")
        for form in (cid, "chat-" + cid):
            res = api_delete("/api/v1/web-dev/workspaces/" + form)
            print("%s -> %s" % (form, res))
            if res.startswith("2"):
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
