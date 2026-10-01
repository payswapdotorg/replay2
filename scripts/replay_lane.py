#!/usr/bin/env python3
"""replay_lane.py — apply an extract_writes manifest onto a verification tree.

§10b/10g doctrine: the Lead re-runs the worker's file ops on a CLEAN pinned
base, then the gates decide landing. This tool replays the manifest's ops in
time order with MULTI-EDIT ATOMICITY (any missing old_str skips the whole
call — but a call whose own tool results show the worker-side ALSO failed is
skipped as state divergence, logged, not fatal).

Usage: replay_lane.py <manifest-dir> <worktree-dir> [--dry]
       manifest-dir — directory produced by extract_writes.py
       worktree-dir — a clean checkout of the pinned base
Exit: 0 = all ops applied (or skipped-as-divergent); 1 = replay broken.
"""
import json
import os
import sys

def load(manifest_dir):
    m = json.load(open(os.path.join(manifest_dir, "manifest.json")))
    ops = []
    for e in m.get("file_ops", []):
        entry = dict(e)
        if entry.get("staged_file"):
            p = os.path.join(manifest_dir, entry["staged_file"])
            if os.path.isfile(p):
                entry["content"] = open(p, encoding="utf-8").read()
        ops.append(entry)
    ops.sort(key=lambda e: (e.get("msg_ts") or 0, e.get("block_ts") or 0,
                            e.get("block", 0), e.get("call", 0)))
    return ops


def failed_worker_side(e):
    """The worker's own tool results show the call failed — state divergence."""
    head = (e.get("result_head") or "").lower()
    return ("no replacement was performed" in head
            or "string to replace not found" in head
            or "not found in file" in head)


def apply_ops(ops, root, dry=False):
    applied = skipped = divergent = 0
    for e in ops:
        fp = e.get("filepath") or ""
        if not fp:
            continue
        # normalize pod paths -> worktree-relative
        rel = fp
        for marker in ("/project/", "/workspace/", "/home/z/my-project/"):
            i = rel.find(marker)
            if i >= 0:
                rel = rel[i + len(marker):]
                break
        # strip a repo subdir prefix if the worktree IS the repo
        for prefix in ("YOU/", "you/"):
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break
        target = os.path.join(root, rel)
        if e["kind"] == "write":
            content = e.get("content")
            if content is None:
                print(f"  [skip] write {rel} — content not staged")
                skipped += 1
                continue
            if dry:
                print(f"  [dry] write {rel} ({len(content)} chars)")
            else:
                os.makedirs(os.path.dirname(target) or root, exist_ok=True)
                open(target, "w", encoding="utf-8").write(content)
            applied += 1
        elif e["kind"] in ("edit", "multiedit"):
            if not os.path.isfile(target):
                print(f"  [skip] {e['kind']} {rel} — target missing (base drift?)")
                skipped += 1
                continue
            if failed_worker_side(e):
                print(f"  [divergence] {e['kind']} {rel} — worker-side failure, skipping")
                divergent += 1
                continue
            src = open(target, encoding="utf-8").read()
            edits = []
            if e["kind"] == "edit":
                a = e.get("args") or {}
                old = a.get("old_str") or a.get("old_string")
                new = a.get("new_str") or a.get("new_string")
                if old is None:
                    print(f"  [skip] edit {rel} — no old_str recorded")
                    skipped += 1
                    continue
                edits = [(old, new or "")]
            else:
                a = e.get("args") or {}
                for ed in (a.get("edits") or []):
                    old = ed.get("old_str") or ed.get("old_string")
                    new = ed.get("new_str") or ed.get("new_string")
                    if old is None:
                        continue
                    edits.append((old, new or ""))
            ok = True
            out = src
            for old, new in edits:
                if old not in out:
                    print(f"  [skip] {e['kind']} {rel} — old_str missing (atomicity)")
                    ok = False
                    skipped += 1
                    break
                out = out.replace(old, new, 1)
            if ok and not dry:
                open(target, "w", encoding="utf-8").write(out)
            if ok:
                applied += 1
    return applied, skipped, divergent


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    manifest_dir, root = sys.argv[1], sys.argv[2]
    dry = "--dry" in sys.argv
    ops = load(manifest_dir)
    print(f"replaying {len(ops)} ops onto {root}{' (dry)' if dry else ''}")
    applied, skipped, divergent = apply_ops(ops, root, dry)
    print(f"applied={applied} skipped={skipped} divergent={divergent}")
    return 0 if applied or divergent else 1


if __name__ == "__main__":
    sys.exit(main())
