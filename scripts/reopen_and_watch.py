#!/usr/bin/env python3
"""reopen_and_watch.py — re-open a browser tab on a SURVIVING server-side
chat and arm queue_watch for it (post-reset re-registration, reset5 epoch).

Usage: reopen_and_watch.py <chat-uuid> <name> [marker]
Exit 0 = tab open + registry record + queue_watch armed.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
PY = sys.executable


def log(m):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}", flush=True)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    chat_id, name = sys.argv[1], sys.argv[2]
    marker = sys.argv[3] if len(sys.argv) > 3 else "END REPORT"

    url = f"https://chat.z.ai/c/{chat_id}"
    tab = channel.new_tab()
    if not tab:
        log("could not open a new tab")
        return 1
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        c.call("Page.navigate", {"url": url}, timeout=30)
        time.sleep(8)
    finally:
        c.close()
    # verify the tab actually landed on the chat
    ok = False
    for t in channel.list_tabs():
        if t.get("id") == tab.get("id") and chat_id[:8] in (t.get("url") or ""):
            ok = True
    if not ok:
        log(f"tab did not navigate to {url} — url now: "
            f"{next((t.get('url') for t in channel.list_tabs() if t.get('id') == tab.get('id')), '?')}")
        return 1

    os.makedirs(FLAGS, exist_ok=True)
    rec = {
        "name": name, "tab_id": tab["id"], "url": url,
        "ts": int(time.time()), "prompt_file": "(post-reset survivor)",
        "mode": "agents-tab", "model": "GLM-5.3", "skill": "Full-Stack",
        "note": "reset5 re-registration of surviving server-side session",
    }
    with open(REG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    log(f"registered {name} -> tab {tab['id'][:8]} chat {chat_id[:8]}")

    rc = subprocess.run([PY, os.path.join(BASE, "launch_queue_watch.py"),
                         name, tab["id"][:8], marker],
                        capture_output=True, text=True, timeout=120)
    log((rc.stdout or "").strip() or (rc.stderr or "").strip())
    return rc.returncode


if __name__ == "__main__":
    sys.exit(main())
