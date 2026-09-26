#!/usr/bin/env python3
"""r30b_dup_route.py — try routing to the duplicate chat via the sidebar
(deep-links bounce on fresh tabs; in-app navigation may not)."""
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

TARGET_SUB = "19499279"


def main():
    # a hydrated home tab
    tabs = [t for t in channel.list_tabs()
            if (t.get("url") or "").rstrip("/") == "https://chat.z.ai"]
    if not tabs:
        print("no home tab")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
    try:
        # click the conversation-list entry whose href contains the target
        r = c.eval("""
(() => {
  const links = [...document.querySelectorAll('a[href*="/c/"]')];
  const target = links.find(a => a.href.includes('%s'));
  if (!target) return JSON.stringify({found: false, n_links: links.length});
  target.click();
  return JSON.stringify({found: true, clicked: true, href: target.href.slice(-20)});
})()
""" % TARGET_SUB, timeout=12)
        print("click:", r)
        time.sleep(6)
        # where are we now + is the thread there?
        r2 = c.eval("""
(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({
    url: location.href.slice(-25),
    hasPacket: t.includes('R30-B: THE ACCOUNT-CHROME FAMILY'),
    hasNoResp: t.includes('No response'),
    bodyLen: t.length
  });
})()
""", timeout=12)
        print("after:", r2)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
