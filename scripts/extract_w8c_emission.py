#!/usr/bin/env python3
"""extract_w8c_emission.py — reconstruct the W8C deliverable from the
in-chat DELIVERY REPORT (block 252 of the batch dump).

Parses:
  - 19 NEW files: path-anchor line + following fenced block (verbatim)
  - 3 MODIFIED files (contractSeam.ts, src/index.ts, index.ts) per the
    report's own modification instructions (base@2e3e68b + changes)

Writes the tree into /home/z/likewise on the you/w8c-automation branch
(branch is at base; files staged, ready to commit).

Usage: extract_w8c_emission.py <report.txt> <repo-root>
"""
import os
import re
import subprocess
import sys

PATH_ANCHOR = re.compile(r"^(packages/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+)\s*$")


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True).stdout


def parse_files(report):
    """Return list of (path, content) for the 19 new files."""
    lines = report.split("\n")
    files = []
    i = 0
    while i < len(lines):
        m = PATH_ANCHOR.match(lines[i].strip())
        if m:
            # next line should be a fence opener
            j = i + 1
            if j < len(lines) and lines[j].strip().startswith("```"):
                # find the closing fence
                k = j + 1
                content = []
                while k < len(lines) and not lines[k].strip() == "```":
                    content.append(lines[k])
                    k += 1
                if k < len(lines):
                    files.append((m.group(1), "\n".join(content) + "\n"))
                    i = k + 1
                    continue
        i += 1
    return files


def fence_after(lines, idx):
    """Extract the first fenced block starting at/after lines[idx]; return (content, end_idx)."""
    j = idx
    while j < len(lines) and not lines[j].strip().startswith("```"):
        j += 1
    k = j + 1
    content = []
    while k < len(lines) and lines[k].strip() != "```":
        content.append(lines[k])
        k += 1
    return "\n".join(content), k + 1


def main():
    report_path, repo = sys.argv[1], sys.argv[2]
    report = open(report_path, encoding="utf-8").read()
    lines = report.split("\n")

    # --- 19 new files ---
    new_files = parse_files(report)
    print(f"new files parsed: {len(new_files)}")
    for p, c in new_files:
        print(f"  {p} ({len(c.splitlines())} lines)")

    # --- contractSeam.ts reconstruction ---
    i_cs = next(i for i, l in enumerate(lines)
                if l.startswith("packages/you-lab/src/contractSeam.ts (MODIFIED"))
    i_idx = next(i for i, l in enumerate(lines)
                 if l.startswith("packages/you-lab/src/index.ts (MODIFIED"))
    cs_lines = lines[i_cs:i_idx]

    # find sub-section fences by their instruction lines
    hdr_start = next(i for i, l in enumerate(cs_lines) if l.startswith("Header comment"))
    header, p1 = fence_after(cs_lines, hdr_start + 1)
    fro_start = next(i for i, l in enumerate(cs_lines) if l.startswith("Frozen-contract import"))
    frozen_add, p2 = fence_after(cs_lines, fro_start + 1)
    neu_start = next(i for i, l in enumerate(cs_lines) if l.startswith("New neutral-type imports"))
    neutral_add, p3 = fence_after(cs_lines, neu_start + 1)
    w8c_start = next(i for i, l in enumerate(cs_lines) if l.startswith("W8C section appended"))
    w8c_section, _ = fence_after(cs_lines, w8c_start + 1)

    base_cs = sh("git", "show", "2e3e68b:packages/you-lab/src/contractSeam.ts", cwd=repo)
    base_cs_lines = base_cs.split("\n")

    # 1. replace the header: base's first 2 lines (verify they're the old header)
    assert "SINGLE seam" in base_cs_lines[0] or "SINGLE seam" in base_cs_lines[1], \
        f"unexpected base header: {base_cs_lines[:2]}"
    out = header.split("\n") + base_cs_lines[2:]

    # 2. frozen-import additions: inside the import type block ending with
    #    } from "../../shared/src/you/contract.js";
    end_marker = '} from "../../shared/src/you/contract.js";'
    ei = next(i for i, l in enumerate(out) if l == end_marker)
    add_lines = [l for l in frozen_add.split("\n") if l.strip()]
    out = out[:ei] + add_lines + out[ei:]

    # 3. neutral-type imports: after the realtime import (find the import
    #    ending 'from "./realtime/...' or the last import-from line before
    #    the first non-import statement)
    rt = None
    for i, l in enumerate(out):
        if re.match(r'^import .* from "\./realtime/', l) or re.match(r'^} from "\./realtime/', l):
            rt = i
    if rt is None:
        # fallback: last import line in the head region
        for i, l in enumerate(out[:400]):
            if l.startswith("} from \"./") or l.startswith("import "):
                rt = i
    out = out[:rt + 1] + neutral_add.split("\n") + out[rt + 1:]

    # 4. append the W8C section at end
    while out and out[-1] == "":
        out.pop()
    out = out + [""] + w8c_section.split("\n")
    cs_final = "\n".join(out)
    if not cs_final.endswith("\n"):
        cs_final += "\n"
    n_cs = len(cs_final.splitlines())
    print(f"contractSeam.ts reconstructed: {n_cs} lines (target ~1815)")

    # --- src/index.ts reconstruction ---
    i_root = next(i for i, l in enumerate(lines)
                  if l.startswith("packages/you-lab/index.ts (MODIFIED"))
    idx_lines = lines[i_idx:i_root]
    ins_start = 0
    idx_add, _ = fence_after(idx_lines, ins_start)
    base_idx = sh("git", "show", "2e3e68b:packages/you-lab/src/index.ts", cwd=repo)
    anchor = '} from "./contractSeam.js";'
    bi = base_idx.split("\n")
    ai = [i for i, l in enumerate(bi) if l.strip() == anchor.strip()]
    assert ai, "anchor not found in base src/index.ts"
    insert_at = ai[-1] + 1
    add = [l for l in idx_add.split("\n")]
    if add and add[0] == "":
        add = add[1:]
    if add and add[-1] == "":
        add = add[:-1]
    out_idx = bi[:insert_at] + add + bi[insert_at:]
    idx_final = "\n".join(out_idx)
    if not idx_final.endswith("\n"):
        idx_final += "\n"
    print(f"src/index.ts reconstructed: {len(idx_final.splitlines())} lines")

    # --- root index.ts: full final content ---
    root_lines = lines[i_root:]
    root_content, _ = fence_after(root_lines, 1)
    print(f"index.ts (root) full content: {len(root_content.splitlines())} lines")

    # --- write everything ---
    written = []
    for p, c in new_files:
        fp = os.path.join(repo, p)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, "w", encoding="utf-8", newline="\n").write(c)
        written.append(p)
    for p, c in (("packages/you-lab/src/contractSeam.ts", cs_final),
                 ("packages/you-lab/src/index.ts", idx_final),
                 ("packages/you-lab/index.ts", root_content + "\n" if not root_content.endswith("\n") else root_content)):
        fp = os.path.join(repo, p)
        open(fp, "w", encoding="utf-8", newline="\n").write(c)
        written.append(p)

    print(f"TOTAL written: {len(written)} files")
    st = sh("git", "status", "--short", cwd=repo)
    print("git status:")
    print(st[:2000])


if __name__ == "__main__":
    main()
