#!/usr/bin/env python3
"""stitch_harvest.py <session-name> — fine-grained virtualization-safe harvest.

The chat virtualizes long messages: only the chunk near the viewport renders.
harvest_report.py samples 4 positions and keeps the longest SINGLE capture —
clipped. This tool scrolls in fine steps, captures the last chat-assistant
innerText at EVERY position, and merges per-file (each file anchor block is
taken from the capture where it is LONGEST — the position where that block
fully rendered).
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import dispatch_worker as _dw

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, "worker-reports")

PATH_RE = re.compile(r"^((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+)(\s*\([^)]*\))?\s*$")
LANG_LINE_RE = re.compile(r"^(rust|toml|json|yaml|text|bash|sh|markdown|md|rs|toml§)$", re.IGNORECASE)


def scroll_and_extract(c, pos):
    c.eval(
        "(() => { const sc = document.querySelector('[class*=scroll]') ||"
        f" document.scrollingElement; sc.scrollTop = sc.scrollHeight * {pos}; return 1; }})()",
        timeout=8)
    time.sleep(1.2)
    return c.eval(
        "(() => { const cs = [...document.querySelectorAll('[class*=chat-assistant]')];"
        " const cont = cs[cs.length-1]; return (cont && cont.innerText) || ''; })()",
        timeout=25) or ""


def parse_blocks(text):
    """Return {path: block_text} from a capture (longest-emission semantics)."""
    lines = text.split("\n")
    anchors = []
    for i, ln in enumerate(lines):
        m = PATH_RE.match(ln.strip())
        if m and "/" in m.group(1):
            anchors.append((i, m.group(1)))
    blocks = {}
    for k, (i, path) in enumerate(anchors):
        end = anchors[k + 1][0] if k + 1 < len(anchors) else len(lines)
        gap = end - (i + 1)
        if gap < 3:
            continue  # summary-list entry, not an emission
        block = lines[i + 1:end]
        if block and LANG_LINE_RE.match(block[0].strip()):
            block = block[1:]
        while block and not block[0].strip():
            block.pop(0)
        while block and not block[-1].strip():
            block.pop()
        b = "\n".join(block)
        if path not in blocks or len(b) > len(blocks[path]):
            blocks[path] = b
    return blocks


def main(name):
    s = _dw._find(name)
    if not s:
        print(f"no session {name}")
        return 1
    tab = _dw._tab_for(s)
    if not tab:
        print(f"tab LOST for {name}")
        return 2

    # first find scroll height
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        h = c.eval(
            "(() => { const sc = document.querySelector('[class*=scroll]') ||"
            " document.scrollingElement; return sc ? sc.scrollHeight : 0; })()", timeout=10)
    finally:
        c.close()
    print("scrollHeight:", h)

    merged = {}
    raw_best = ""
    n_steps = 40
    for step in range(n_steps + 1):
        pos = step / n_steps
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            txt = scroll_and_extract(c, pos)
        except Exception as e:
            print(f"pos {pos:.2f}: err {type(e).__name__}")
            c.close()
            continue
        c.close()
        if len(txt) > len(raw_best):
            raw_best = txt
        blocks = parse_blocks(txt)
        grew = []
        for p, b in blocks.items():
            if p not in merged or len(b) > len(merged[p]):
                merged[p] = b
                grew.append(f"{p.split('/')[-1]}:{len(b)}")
        if grew:
            print(f"pos {pos:.2f}: len={len(txt)} grew {grew}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(OUTDIR, exist_ok=True)
    raw_path = os.path.join(OUTDIR, f"{name}-stitched-{stamp}.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_best)
    print(f"raw best -> {raw_path} ({len(raw_best)} chars)")
    files_dir = os.path.join(OUTDIR, f"{name}-stitched-files")
    for p, content in merged.items():
        dest = os.path.join(files_dir, p)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        print(f"file -> {dest} ({len(content)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
