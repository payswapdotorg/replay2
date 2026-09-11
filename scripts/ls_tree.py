#!/usr/bin/env python3
"""ls_tree.py — full sandbox file tree via the workspaces files API.

Usage: ls_tree.py <raw-chat-uuid> <workspace-id> [prefix]
Lesson 24: the files API REJECTS the chat- prefix — pass the RAW uuid.
"""
import json
import sys

sys.path.insert(0, '/home/z/replay2/scripts')
import channel


def page_eval(js, timeout=60):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()


def main():
    raw_uuid = sys.argv[1].replace("chat-", "")
    workspace = sys.argv[2]
    js = f"""
    (async () => {{
      const r = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', {{
        method: 'POST',
        credentials: 'include',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{chatId: '{raw_uuid}', workspace_id: '{workspace}'}})
      }});
      const t = await r.text();
      return t.slice(0, 500000);
    }})()
    """
    raw = page_eval(js, timeout=90)
    try:
        d = json.loads(raw)
    except Exception:
        print("RAW[:2000]:", raw[:2000])
        return 1
    tree = d.get("data", d) if isinstance(d, dict) else d
    files = []
    def walk(node, path=""):
        if isinstance(node, dict):
            name = str(node.get("name") or node.get("path") or "")
            if node.get("type") == "file":
                files.append((path + "/" + name).lstrip("/"))
            kids = node.get("children") or node.get("files")
            if isinstance(kids, list):
                for c in kids:
                    walk(c, (path + "/" + name).lstrip("/"))
        elif isinstance(node, list):
            for c in node:
                walk(c, path)
    walk(tree)
    if not files and isinstance(tree, dict):
        # maybe flat list of {path:...}
        flat = tree.get("tree") or tree.get("files") or tree.get("list")
        if isinstance(flat, list):
            for f in flat:
                if isinstance(f, dict):
                    files.append(str(f.get("path") or f.get("name")))
                else:
                    files.append(str(f))
    print(f"files: {len(files)}")
    for f in sorted(files):
        print(" ", f[:120])
    if not files:
        print("RAW SHAPE[:1500]:", raw[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
