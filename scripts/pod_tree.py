#!/usr/bin/env python3
"""pod_tree.py <raw-chat-uuid> <workspace-id> [filter-substr]
Full (untruncated) ls-tree of a worker pod; optional substring filter."""
import json
import sys

sys.path.insert(0, '/home/z/replay2/scripts')
import channel


def main():
    raw_uuid = sys.argv[1].replace("chat-", "")
    workspace = sys.argv[2]
    filt = sys.argv[3] if len(sys.argv) > 3 else None
    js = f"""
    (async () => {{
      const r = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{chatId: '{raw_uuid}', workspace_id: '{workspace}'}})
      }});
      const t = await r.text();
      return t.slice(0, 2000000);
    }})()
    """
    tab = channel.find_tab("chat.z.ai")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        raw = ws.eval(js, await_promise=True, timeout=120)
    finally:
        ws.close()
    try:
        arr = json.loads(raw)
        if isinstance(arr, dict):
            arr = arr.get("data", arr)
    except Exception as e:
        print("PARSE FAIL:", e)
        print(raw[:3000])
        return 1
    print("total entries:", len(arr))
    for p in arr:
        if filt is None or filt.lower() in p.lower():
            print(" ", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
