#!/usr/bin/env python3
"""check_turn_dom.py <url-substring> — live DOM state of a chat tab (generating
indicator, body length, tail snippet, error banners)."""
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, find_tab  # noqa: E402

needle = sys.argv[1] if len(sys.argv) > 1 else "chat.z.ai"
tab = find_tab(needle)
if not tab:
    print("no tab for", needle)
    sys.exit(0)
cdp = CDP(tab["webSocketDebuggerUrl"])
expr = r"""JSON.stringify({
  url: location.href.slice(0, 90),
  stopBtn: !!document.querySelector('button[class*="stop"], [data-testid*="stop"]'),
  errBanners: Array.from(document.querySelectorAll('[class*="error"],[class*="Error"]'))
    .map(e => e.innerText.trim().slice(0, 90)).filter(t => t.length > 3).slice(0, 4),
  bodyLen: document.body.innerText.length,
  tail: document.body.innerText.slice(-350).replace(/[\n\r]+/g, " | ")
})"""
print(cdp.eval(expr))
cdp.close()
