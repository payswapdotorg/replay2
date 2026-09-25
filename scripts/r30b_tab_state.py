#!/usr/bin/env python3
"""r30b_tab_state.py — read the worker tab's DOM truth (lesson-138 liveness).

Usage: r30b_tab_state.py <chat-id-substr>
Opens (or reuses) a tab on the chat and prints bodyLen / no-response /
streaming / tail. The tab DOM is the only reliable liveness for agent chats.
"""
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = """
(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({
    bodyLen: t.length,
    noResp: t.includes('No response'),
    streaming: !!document.querySelector('[class*=generating]'),
    last: t.trim().split('\\n').slice(-2).join(' ~ ').slice(0, 180)
  });
})()
"""


def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else "d5e9e1ec"
    tabs = [t for t in channel.list_tabs() if sub in (t.get("url") or "")]
    fresh = False
    if tabs:
        t = tabs[0]
    else:
        t = channel.new_tab(f"https://chat.z.ai/c/{sub}"
                            if len(sub) == 36 else
                            "https://chat.z.ai/")
        fresh = True
        time.sleep(10)
        live = {x["id"]: x for x in channel.list_tabs()}
        t2 = live.get(t["id"])
        if not t2:
            print("TAB DIED")
            return 1
        t = t2
    try:
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
        try:
            r = c.eval(JS, timeout=12)
            print(("FRESH " if fresh else "REUSED ") + f"{t['id'][:10]}: {r}")
            return 0
        finally:
            c.close()
    except Exception as e:
        print(f"{t['id'][:10]} EVAL-DEAD ({type(e).__name__})")
        return 2


if __name__ == "__main__":
    sys.exit(main())
