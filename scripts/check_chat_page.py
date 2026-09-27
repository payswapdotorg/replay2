#!/usr/bin/env python3
"""check_chat_page.py — quick chat.z.ai page state via CDP (title + sign-in presence)."""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
from channel import CDP, find_tab  # noqa: E402

tab = find_tab("chat.z.ai")
if not tab:
    print("no chat tab")
    sys.exit(0)
cdp = CDP(tab["webSocketDebuggerUrl"])
expr = (
    "JSON.stringify({"
    "title: document.title.slice(0,60), "
    "url: location.href.slice(0,80), "
    "signin: document.body.innerText.toLowerCase().includes('sign in'), "
    "snippet: document.body.innerText.slice(0,180).replace(/[\\n\\r]+/g,' | ')"
    "})"
)
print(cdp.eval(expr))
cdp.close()
