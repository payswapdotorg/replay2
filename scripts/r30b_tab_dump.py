#!/usr/bin/env python3
"""r30b_tab_dump.py — dump the worker tab's thread tail + buttons (file-based
to dodge shell quoting; lesson: inline -c JS is a SyntaxError factory)."""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = """
(() => {
  const t = (document.body.innerText || '');
  const lines = t.trim().split('\\n');
  const btns = [...document.querySelectorAll('button')]
    .map(b => (b.innerText || '').trim())
    .filter(x => x && x.length < 30);
  return JSON.stringify({tail: lines.slice(-14),
                         buttons: [...new Set(btns)].slice(0, 30)});
})()
"""


def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else "d5e9e1ec"
    tabs = [t for t in channel.list_tabs() if sub in (t.get("url") or "")]
    if not tabs:
        print("NOTAB")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
    try:
        r = c.eval(JS, timeout=12)
        d = json.loads(r)
        print("TAIL:")
        for line in d["tail"]:
            print("  |", line[:110])
        print("BUTTONS:", d["buttons"])
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
