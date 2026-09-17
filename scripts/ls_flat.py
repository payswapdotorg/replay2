#!/usr/bin/env python3
"""ls_flat.py — flat workspace ls-tree parser (lesson-118 recovery rail).

The workspaces files API `ls-tree` returns a FLAT array of file-path
strings (not a nested tree — ls_tree.py's nested walker truncates and
hides subtrees). This tool prints the flat list, optionally filtered
by a path prefix (e.g. `sporta`), with counts and sporta-path totals.

Usage:  ls_flat.py <chat-id> <workspace-id> [prefix-filter]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402


def eval_retry(cdp, js, tries=6, timeout=90):
    last = None
    for i in range(tries):
        try:
            return cdp.eval(js, await_promise=True, timeout=timeout)
        except Exception as e:
            last = e
            time.sleep(2 + i * 2)
    raise last


def ls_flat(chat_id: str, workspace_id: str):
    tab = channel.find_tab("chat.z.ai")
    cdp = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        payload = json.dumps({"chatId": chat_id, "workspace_id": workspace_id})
        js = f"""
        (async () => {{
          const r = await fetch('/api/v1/web-dev/workspaces/files/ls-tree', {{
            method:'POST', credentials:'include',
            headers:{{'Content-Type':'application/json'}},
            body: JSON.stringify({payload})
          }});
          return await r.text();
        }})()
        """
        raw = eval_retry(cdp, js)
        tree = json.loads(raw)
        if isinstance(tree, list):
            return [f for f in tree if isinstance(f, str)]
        return []
    finally:
        cdp.close()


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    chat_id, ws = sys.argv[1], sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else None
    files = ls_flat(chat_id, ws)
    print(f"tree: {len(files)} files")
    if prefix:
        match = [f for f in files if f.startswith(prefix)]
        print(f"matching {prefix!r}: {len(match)}")
        for f in match[:400]:
            print(" ", f)
        if len(match) > 400:
            print(f"  ... (+{len(match)-400} more)")
    else:
        for f in files[:200]:
            print(" ", f)
        if len(files) > 200:
            print(f"  ... (+{len(files)-200} more)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
