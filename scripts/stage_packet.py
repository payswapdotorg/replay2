#!/usr/bin/env python3
"""stage_packet.py <TXXX> — resolve __DISPATCH_BASE__ and stage a packet for send.

The wave-29 packets (pkt_T035.md, pkt_T041.md, ...) carry the placeholder
__DISPATCH_BASE__ because their dispatch base (origin/main HEAD) is only
known at send time — they are dispatched AFTER other tickets merge, which
moves main. This helper:

1. Reads origin/main HEAD from the local TradRL clone (fetches first).
2. Reads the packet from the persistent replay-state/ store.
3. Refuses to stage if:
   - the packet has no __DISPATCH_BASE__ placeholder (already staged?), or
   - a literal ghp_ token is present (must stay [REDACTED:github_token]
     until dispatch_worker._subst_pat at send time), or
   - the base SHA is not a 40-hex string.
4. Writes scripts/flags/pkt_<TXXX>_staged.md (600) with the base resolved.

Usage:  python3 stage_packet.py T035
Then:   python3 dispatch_worker.py create T035 flags/pkt_T035_staged.md

Rebuilt verbatim 2026-10-03 after reset-4 rolled the tree back.
"""
import os
import re
import subprocess
import sys

MY = "/home/z/my-project"
REPO = "/home/z/TradRL"
FLAGS = "/home/z/replay2/scripts/flags"


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"T\d{3}", sys.argv[1]):
        print("usage: stage_packet.py <TXXX>")
        return 2
    name = sys.argv[1]
    src = os.path.join(MY, "replay-state", f"pkt_{name}.md")
    if not os.path.exists(src):
        print(f"FATAL: {src} missing")
        return 1
    text = open(src, encoding="utf-8").read()

    if "__DISPATCH_BASE__" not in text:
        print(f"FATAL: {src} has no __DISPATCH_BASE__ placeholder "
              "(already resolved? refuse to double-stage)")
        return 1
    if re.search(r"ghp_[A-Za-z0-9]{20,}", text):
        print("FATAL: literal token in packet — must remain "
              "[REDACTED:github_token] until send time")
        return 1

    subprocess.run(["git", "-C", REPO, "fetch", "origin"],
                   capture_output=True, timeout=120)
    r = subprocess.run(["git", "-C", REPO, "rev-parse", "origin/main"],
                       capture_output=True, text=True, timeout=30)
    sha = r.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        print(f"FATAL: origin/main unresolved: {sha[:60]!r}")
        return 1

    n = text.count("__DISPATCH_BASE__")
    text = text.replace("__DISPATCH_BASE__", sha)
    out = os.path.join(FLAGS, f"pkt_{name}_staged.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(out, 0o600)
    print(f"STAGED {name}: base={sha[:12]} ({n} placeholder(s) resolved)")
    print(f"send with: cd /home/z/replay2/scripts && "
          f"python3 dispatch_worker.py create {name} flags/pkt_{name}_staged.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
