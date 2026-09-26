#!/usr/bin/env python3
"""r30b_marker_check.py — search the whole worker page for the completion
marker + report the streaming state."""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = """
(() => {
  const t = document.body.innerText || '';
  const idx = t.indexOf('=== R30-B COMPLETION REPORT ===');
  return JSON.stringify({
    bodyLen: t.length,
    marker: idx >= 0,
    markerTail: idx >= 0 ? t.slice(idx, idx + 400) : null,
    streaming: !!document.querySelector('[class*=generating]'),
    shaLine: (t.match(/[0-9a-f]{40}/g) || []).slice(0, 3),
    hasPush: /pushed|git push/i.test(t.slice(-3000)),
    tail: t.trim().split('\\n').slice(-3).join(' ~ ').slice(0, 200)
  });
})()
"""


def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else "dd5c60bf"
    tabs = [t for t in channel.list_tabs() if sub in (t.get("url") or "")]
    if not tabs:
        print("NOTAB")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
    try:
        r = c.eval(JS, timeout=12)
        print(r[:900])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
