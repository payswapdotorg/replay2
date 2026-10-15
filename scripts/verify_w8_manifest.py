#!/usr/bin/env python3
"""verify_w8_manifest.py <MANIFEST-path> <bundle-dir> — the A-PROD-006-W8
station-side delivery verifier (never trust reported numbers).

Verifies the worker delivery against the frozen work-order contract:
  1. the bundle carries EXACTLY one ref: refs/heads/flauz-aprod/aprod-006-w8
  2. single commit whose parent IS the pinned BASE c5646075...
  3. every MANIFEST changed-file row: sha256(blob at branch head) matches
  4. the changed-file set == git diff --name-only BASE..branch (both ways)
  5. TREE-SELF-CHECK: sha256 of the branch tree hash (git write-tree output)
     matches — newline and no-newline forms both accepted
  6. GATE-FROZEN law: the three named instruments are byte-identical
     BASE <-> branch head, and no instrument appears in the changed set

Exit 0 ONLY if every hard check passes. Prints a receipt table for banking.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

BASE = "c56460755b59e425a23992039c818cd60ac070a7"
BRANCH = "flauz-aprod/aprod-006-w8"
INSTRUMENTS = [
    "build/flauz/scripts/packaging-parity.mjs",
    "build/flauz/scripts/compat-battery.mjs",
    "build/flauz/scripts/agentos-battery.mjs",
]
SHA_RE = re.compile(r"\b([0-9a-f]{64})\b")
HEX40_RE = re.compile(r"\b([0-9a-f]{40})\b")


def run(cmd, cwd=None, timeout=120):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def blob_sha256(repo, ref, path):
    # RAW bytes — never through the text/strip path (trailing newlines are
    # part of the blob; stripping them silently changes the hash)
    r = subprocess.run(["git", "show", f"{ref}:{path}"],
                       capture_output=True, cwd=repo, timeout=120)
    if r.returncode != 0:
        return None
    return hashlib.sha256(r.stdout).hexdigest()


def parse_manifest(text):
    """Tolerant parse: rows of (sha256, path); TREE-SELF-CHECK value."""
    rows = []
    tree_check = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("TREE-SELF-CHECK"):
            m = SHA_RE.search(s)
            if m:
                tree_check = m.group(1)
            continue
        m = SHA_RE.search(s)
        if not m:
            continue
        sha = m.group(1)
        rest = s[: m.start()] + s[m.end():]
        path = rest.strip().lstrip("*").strip()
        path = re.sub(r"^[-–—|:\s]+", "", path).strip()
        path = path.strip("`\"'").strip()
        if not path or path.startswith("#"):
            continue
        if HEX40_RE.fullmatch(path) or " " in path:
            # take the first whitespace-free token that looks like a path
            toks = [t for t in re.split(r"[\s|]+", rest) if t]
            cand = [t for t in toks if not HEX40_RE.fullmatch(t) and "/" in t or t.count(".") >= 1]
            if not cand:
                continue
            path = cand[0].strip("`\"'*:,-")
        rows.append((sha, path))
    return rows, tree_check


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    man_path = os.path.abspath(sys.argv[1])
    bundle_dir = os.path.abspath(sys.argv[2])
    bundle = os.path.join(bundle_dir, "aprod-006-w8.bundle")
    if not os.path.exists(man_path):
        print(f"FAIL: MANIFEST not found: {man_path}")
        return 2
    if not os.path.exists(bundle):
        print(f"FAIL: bundle not found: {bundle}")
        return 2

    text = open(man_path, encoding="utf-8", errors="replace").read()
    rows, tree_check = parse_manifest(text)
    print(f"manifest rows parsed: {len(rows)}; TREE-SELF-CHECK: {'present' if tree_check else 'MISSING'}")

    receipts = []
    ok = True

    def bank(check, verdict, detail=""):
        nonlocal ok
        if not verdict:
            ok = False
        receipts.append((check, "PASS" if verdict else "FAIL", detail))

    with tempfile.TemporaryDirectory(prefix="w8-verify-") as repo:
        rc, out, err = run(["git", "init", "-q", repo])
        bank("scratch repo init", rc == 0, err[:120])
        # 1. bundle ref surface
        rc, out, err = run(["git", "bundle", "list-heads", bundle], cwd=repo)
        heads = [l.split()[1] for l in out.splitlines() if l.strip()]
        bank("bundle single ref == flauz-aprod/aprod-006-w8",
             heads == [f"refs/heads/{BRANCH}"], f"heads={heads}")
        # fetch the branch from the bundle; a THIN bundle (BASE..branch form)
        # fails on prerequisites in an empty repo — pre-seed BASE from the
        # station's flauz clone and retry (both bundle shapes are accepted;
        # full-history bundles die at pack-objects under memory pressure)
        rc, out, err = run(["git", "fetch", "-q", bundle, f"refs/heads/{BRANCH}:refs/heads/{BRANCH}"], cwd=repo, timeout=600)
        if rc != 0 and "prerequisite" in (err + out).lower():
            seed_src = os.environ.get("FLAUZ_CLONE", "/home/z/Flauz")
            rc2, _o, e2 = run(["git", "fetch", "-q", "--depth=1", seed_src, BASE], cwd=repo, timeout=600)
            print(f"thin bundle detected — seeded BASE from {seed_src} (rc={rc2} {e2[:80]})")
            rc, out, err = run(["git", "fetch", "-q", bundle, f"refs/heads/{BRANCH}:refs/heads/{BRANCH}"], cwd=repo, timeout=600)
        bank("fetch branch from bundle", rc == 0, err[:200])
        if rc != 0:
            for c, v, d in receipts:
                print(f"  {v}  {c}  {d}")
            return 1
        rc, head, _ = run(["git", "rev-parse", f"refs/heads/{BRANCH}"], cwd=repo)
        print(f"branch head: {head}")
        # 2. parent == BASE, single commit
        rc, parent, _ = run(["git", "rev-parse", f"refs/heads/{BRANCH}^"], cwd=repo)
        bank("parent == pinned BASE", parent == BASE, f"parent={parent[:12]}")
        rc, count, _ = run(["git", "rev-list", "--count", f"{BASE}..refs/heads/{BRANCH}"], cwd=repo)
        bank("single commit on branch", count == "1", f"count={count}")
        # 4. changed set both ways
        rc, diff_out, _ = run(["git", "diff", "--name-only", f"{BASE}", f"refs/heads/{BRANCH}"], cwd=repo)
        changed = set(l.strip() for l in diff_out.splitlines() if l.strip())
        man_paths = set(p for _s, p in rows)
        man_changed = set(p for p in man_paths if p in changed or p not in _base_paths(repo, BASE, man_paths))
        missing_rows = changed - man_paths
        extra_rows = man_paths - changed - set(INSTRUMENTS)
        bank("manifest covers every changed file", not missing_rows,
             f"missing={sorted(missing_rows)[:5]}")
        bank("manifest rows all real diffs (or frozen instruments)", not extra_rows,
             f"extra={sorted(extra_rows)[:5]}")
        # 3. per-row sha256
        bad = []
        for sha, path in rows:
            if path in INSTRUMENTS:
                continue  # frozen instruments checked separately
            got = blob_sha256(repo, f"refs/heads/{BRANCH}", path)
            if got is None:
                got = blob_sha256(repo, f"refs/heads/{BRANCH}", path)  # retry for exotic names
            if got != sha:
                bad.append((path, (got or "ABSENT")[:12], sha[:12]))
        bank("every changed-file sha256 matches", not bad, f"bad={bad[:4]}")
        # 5. TREE-SELF-CHECK
        rc, tree_hex, _ = run(["git", "rev-parse", f"refs/heads/{BRANCH}^{{tree}}"], cwd=repo)
        if tree_hex:
            nl = hashlib.sha256((tree_hex + "\n").encode()).hexdigest()
            nonl = hashlib.sha256(tree_hex.encode()).hexdigest()
            match = tree_check in (nl, nonl) if tree_check else False
            bank("TREE-SELF-CHECK matches branch tree", bool(tree_check) and match,
                 f"tree={tree_hex[:12]}")
        else:
            bank("TREE-SELF-CHECK matches branch tree", False, "no tree resolved")
        # 6. GATE-FROZEN law
        for inst in INSTRUMENTS:
            at_branch = blob_sha256(repo, f"refs/heads/{BRANCH}", inst)
            at_base = blob_sha256(repo, BASE, inst)
            frozen_ok = at_branch is not None and at_branch == at_base
            listed = next((s for s, p in rows if p == inst), None)
            listed_ok = listed is None or listed == at_branch
            bank(f"GATE-FROZEN byte-identical: {os.path.basename(inst)}",
                 frozen_ok and listed_ok,
                 f"branch={at_branch[:12] if at_branch else 'ABSENT'} base={at_base[:12] if at_base else 'ABSENT'}")
        # bonus receipt: manifest itself
        print(f"\nmanifest sha256: {hashlib.sha256(open(man_path,'rb').read()).hexdigest()}")

    print("\n=== VERIFICATION RECEIPTS ===")
    for c, v, d in receipts:
        print(f"  {v}  {c}  {d}")
    print(f"\nVERDICT: {'CLEAN — delivery verified' if ok else 'DEFECTS FOUND — require-changes'}")
    return 0 if ok else 1


def _base_paths(repo, base, man_paths):
    """Resolve which manifest paths exist at BASE (helper for set math)."""
    rc, out, _ = run(["git", "ls-tree", "-r", "--name-only", base], cwd=repo, timeout=300)
    return set(l.strip() for l in out.splitlines() if l.strip())


if __name__ == "__main__":
    raise SystemExit(main())
