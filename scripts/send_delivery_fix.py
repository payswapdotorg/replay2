#!/usr/bin/env python3
"""send_delivery_fix.py — one-shot: send the delivery-location correction to
the R3 workers (station Task 83, 2026-10-18).

Discovery: the R3 packets told workers to clone to ~/payswap3-0, but the
workspace file API (ls-tree / files/content) indexes ONLY the app root
(where src/, package.json, prisma/ live). Shell-cloned files outside that
root are invisible to the harvest. merchant-A completed with its whole
delivery outside the index and its sandbox was RECYCLED before harvest —
files lost (the duplicate merchant-B is the insurance).

This script sends both live workers the correction: make the delivery
visible in the app-root file tree (git bundle + copies + markers via the
file tools), self-verify against their own file panel before reporting.

Usage: send_delivery_fix.py <chat-url> <msg-file>
"""
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel


def main():
    url, msg_file = sys.argv[1], sys.argv[2]
    msg = open(msg_file).read().strip()
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise SystemExit("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        ws.eval(f"location.href = '{url}'", await_promise=False, timeout=20)
    finally:
        pass
    time.sleep(8)
    # dismiss any overlay dialogs first (the send path does it too, but be sure)
    for _ in range(3):
        try:
            ws.eval("""(() => {
              const roots = document.querySelectorAll('[role=dialog],[data-state=open]');
              for (const r of roots) {
                const btns = [...r.querySelectorAll('button')];
                const later = btns.find(b => /^(maybe later|later|not now|no thanks|dismiss|got it|next|ok)$/i.test((b.innerText||'').trim()));
                if (later) { later.click(); return 'closed'; }
              }
              return 'none';
            })()""", timeout=15)
        except Exception:
            pass
        time.sleep(1)
    ws.close()

    r = channel.send_text(msg, tab=channel.find_tab("chat.z.ai"))
    print("send result:", r)


if __name__ == "__main__":
    main()
