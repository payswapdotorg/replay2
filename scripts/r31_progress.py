#!/usr/bin/env python3
"""r31_progress.py — the DOM-truth progress probe for the R31 worker chat.

Lesson-138 pattern: the messages API only shows committed turns; the live
tab's DOM shows the in-flight truth. Prints the tail of the chat page plus
streaming/tool indicators.
"""
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

SUB = "ca87c5cf"

JS = """
(() => {
  const t = document.body.innerText || '';
  const blocks = [...document.querySelectorAll('[class*=message]')];
  const asst = blocks.filter(b => (b.className||'').includes('assistant'));
  const spin = [...document.querySelectorAll('[class*=loading], [class*=spin], [class*=running], [class*=executing]')].length;
  return JSON.stringify({
    ts: new Date().toISOString(),
    bodyLen: t.length,
    noResp: t.includes('No response'),
    generating: !!document.querySelector('[class*=generating], [class*=streaming]'),
    spinners: spin,
    assistantBlocks: asst.length,
    tail: t.slice(-500)
  });
})()
"""


def main():
    tabs = [t for t in channel.list_tabs() if SUB in (t.get("url") or "")]
    if not tabs:
        print("NOTAB")
        return 1
    c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=20)
    try:
        print(c.eval(JS, timeout=30, await_promise=True))
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
