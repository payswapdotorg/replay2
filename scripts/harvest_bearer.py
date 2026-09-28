#!/usr/bin/env python3
"""harvest_bearer.py <chat-id> <workspace-id> <prefix-or-filepath> <dest-dir>

Lesson-198b: after a browser logout, in-page fetches (cookie auth) 401 on the
web-dev APIs while the cached Bearer JWT still authorizes them DIRECTLY.
This harvester speaks pure urllib + Authorization — no browser, no CDP, no
wedge classes. <prefix-or-filepath> may be a delivery prefix (trailing /)
or an exact file path (single-file mode: dest-dir is treated as the file).
"""
import base64
import json
import os
import sys
import time
import urllib.request

TOKEN = open("/home/z/replay2/scripts/flags/chat_token").read().strip()
BASE = "https://chat.z.ai"


def api(path, body=None, timeout=60):
    req = urllib.request.Request(
        BASE + path, method="POST",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get_tree(chat, ws, tries=6):
    last = None
    for i in range(tries):
        try:
            return api("/api/v1/web-dev/workspaces/files/ls-tree",
                       {"chatId": chat, "workspace_id": ws}, timeout=90)
        except Exception as e:
            last = e
            time.sleep(3 + i * 2)
    raise last


def fetch_file(chat, ws, fp, tries=6):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                BASE + "/api/v1/web-dev/workspaces/files/content",
                method="POST",
                data=json.dumps({"chatId": chat, "workspace_id": ws,
                                 "rev": "latest", "filepath": fp}).encode(),
                headers={"Authorization": f"Bearer {TOKEN}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()  # raw bytes
        except Exception as e:
            last = e
            time.sleep(3 + i * 2)
    raise last


def main():
    chat, ws, target, dest = sys.argv[1:5]
    if target.endswith("/") or not target.endswith(".bundle"):
        # prefix mode: harvest every file under the prefix
        prefix = target.rstrip("/") + "/"
        tree = get_tree(chat, ws)
        files = [f for f in tree if isinstance(f, str) and f.startswith(prefix)]
        print(f"tree: {len(tree)} files; matching {prefix!r}: {len(files)}")
        if not files:
            return 1
        os.makedirs(dest, exist_ok=True)
        ok = skip = fail = 0
        for fp in files:
            rel = fp[len(prefix):]
            d = os.path.join(dest, rel)
            if os.path.exists(d) and os.path.getsize(d) > 0:
                skip += 1
                continue
            try:
                data = fetch_file(chat, ws, fp)
                os.makedirs(os.path.dirname(d) or dest, exist_ok=True)
                with open(d, "wb") as f:
                    f.write(data)
                ok += 1
                if ok % 20 == 0:
                    print(f"  ... {ok}/{len(files)}")
            except Exception as e:
                fail += 1
                print(f"  FAIL {fp}: {str(e)[:80]}")
        print(f"done: fetched={ok} skipped={skip} failed={fail}")
        return 0 if ok + skip > 0 else 1
    else:
        # single-file mode
        d = os.path.dirname(dest)
        if d:
            os.makedirs(d, exist_ok=True)
        try:
            data = fetch_file(chat, ws, target)
            with open(dest, "wb") as f:
                f.write(data)
            print(f"OK {target} -> {dest} ({len(data)} bytes)")
            return 0
        except Exception as e:
            print(f"FAILED {target}: {str(e)[:120]}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
