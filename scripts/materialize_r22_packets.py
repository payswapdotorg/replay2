#!/usr/bin/env python3
"""materialize_r22_packets.py — regenerate the R22 worker dispatch packets
from the committed .template.md files + the recovered PAT flag.

Same doctrine as materialize_r20_r21_packets.py (lesson from the seventh
reset): real .md packets (PAT embedded) live only in the working tree;
templates are committed; the PAT is at scripts/flags/recovered_pat.txt
(600). After ANY reset: re-clone replay2, restore the PAT flag, run this
script — the R22 armory regenerates in seconds.

Usage:
  python3 scripts/materialize_r22_packets.py   # writes R22-W1/W2/W3 .md
"""
import os
import stat
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(BASE, "worker-prompts")
PAT_FLAG = os.path.join(BASE, "flags", "recovered_pat.txt")

PACKETS = ["R22-W1", "R22-W2", "R22-W3"]


def main():
    try:
        with open(PAT_FLAG) as f:
            pat = f.read().strip()
    except OSError:
        print(f"ERROR: PAT flag missing ({PAT_FLAG}) — restore it first", file=sys.stderr)
        return 1
    if not pat or len(pat) < 20:
        print("ERROR: PAT flag looks empty/invalid", file=sys.stderr)
        return 1

    made = []
    for name in PACKETS:
        tpl_path = os.path.join(PROMPTS, f"{name}.template.md")
        out_path = os.path.join(PROMPTS, f"{name}.md")
        try:
            with open(tpl_path, encoding="utf-8") as f:
                tpl = f.read()
        except OSError:
            print(f"ERROR: template missing: {tpl_path}", file=sys.stderr)
            return 1
        if "__GITHUB_PAT__" not in tpl:
            print(f"WARN: {tpl_path} has no __GITHUB_PAT__ placeholder", file=sys.stderr)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(tpl.replace("__GITHUB_PAT__", pat))
        os.chmod(out_path, 0o600)
        made.append(out_path)

    for p in made:
        print(f"materialized: {p} ({os.path.getsize(p)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
