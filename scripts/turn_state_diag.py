#!/usr/bin/env python3
"""Diagnose worker turn state: error banner / thinking / last content."""
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

CHATS = {"w3a": "6b9b7434", "w3b": "e5ad519f", "w3c": "399679e4"}


def main():
    for name, cid in CHATS.items():
        tab = None
        for t in channel.list_tabs():
            if cid in (t.get("url") or ""):
                tab = t
                break
        if not tab:
            print(name, "| TAB NOT FOUND")
            continue
        try:
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        except Exception as e:
            print(name, "| CDP FAIL", str(e)[:50])
            continue
        try:
            noresp = c.eval(
                "document.body.innerText.slice(-3000).includes('No response')",
                timeout=15)
            think = c.eval(
                "document.body.innerText.slice(-1500).includes('Thinking')",
                timeout=15)
            tail = c.eval(
                "document.body.innerText.slice(-250)", timeout=15) or ""
            c.close()
        except Exception as e:
            print(name, "| EVAL FAIL", str(e)[:50])
            c.close()
            continue
        print("%s | noResponse=%s thinking=%s | tail=%r"
              % (name, noresp, think, tail.replace("\n", " | ")))


if __name__ == "__main__":
    main()
