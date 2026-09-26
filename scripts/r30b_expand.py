#!/usr/bin/env python3
"""r30b_expand.py — click every 'Show full message' expander on the worker
page, then read the TRUE tail (the full latest turn)."""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS_EXPAND = """
(() => {
  const btns = [...document.querySelectorAll('button')]
    .filter(b => (b.innerText || '').trim() === 'Show full message');
  btns.forEach(b => b.click());
  return String(btns.length);
})()
"""

JS_TAIL = """
(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({
    bodyLen: t.length,
    tail: t.trim().split('\\n').slice(-16).join('\\n').slice(0, 1400)
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
        n = c.eval(JS_EXPAND, timeout=12)
        print(f"expanded {n} messages")
        time.sleep(2)
        r = c.eval(JS_TAIL, timeout=12)
        d = json.loads(r)
        print(f"bodyLen={d['bodyLen']}")
        print("TRUE TAIL:")
        print(d["tail"])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
