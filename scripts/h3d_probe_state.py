#!/usr/bin/env python3
"""h3d_probe_state.py — quick studio state probe."""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, list_tabs  # noqa: E402


def main():
    tabs = [t for t in list_tabs() if "3212" in (t.get("url") or "")]
    if not tabs:
        print("no tab")
        return 1
    ws = CDP(tabs[0]["webSocketDebuggerUrl"])
    try:
        expr = r"""JSON.stringify({
          studio: !!document.querySelector("div[role=dialog][aria-label='Rodin Studio workspace']"),
          appErr: document.body.innerText.includes('Application error'),
          credit: (document.body.innerText.match(/(\d+)\s*\n?credits/i) || [])[1] || null,
          hasPosterImg: !!document.querySelector('img[src*="preview"]'),
          hasCanvas: document.querySelectorAll('canvas').length,
          hasExportUi: /Export|Download/i.test(document.body.innerText),
          bodyTail: document.body.innerText.slice(-220).replace(/\n+/g, ' | ')
        })"""
        print(ws.eval(expr, timeout=20))
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    sys.exit(main())
