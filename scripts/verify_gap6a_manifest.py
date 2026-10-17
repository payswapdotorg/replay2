#!/usr/bin/env python3
"""verify_gap6a_manifest.py <MANIFEST-path> <bundle-dir> [--base <sha>] —
the GAP-6A station-side delivery verifier (never trust reported numbers).

Verifies the worker delivery against the frozen work-order contract:
  1. the bundle carries EXACTLY one ref: refs/heads/flauz-tlb/dh-gap6a-bgux
  2. single commit whose parent IS the declared BASE (default the pinned
     71e2041...; the report's BASE when --base passed) AND the parent is a
     real ancestor of origin/main (the rebase honesty check — the local
     /home/z/flauz clone is the witness)
  3. every MANIFEST changed-file row: sha256(blob at branch head) matches
  4. the changed-file set == git diff --name-only BASE..branch (both ways)
  5. TREE-SELF-CHECK: sha256 of the branch tree hash (git write-tree output)
     matches — newline and no-newline forms both accepted
  6. THE FROZEN-15 LAW: the fifteen frozen modules (6 ZC-002 contract
     families + 6 ZC-001 projections + 3 authority seams) are byte-identical
     BASE <-> branch head, and NONE appears in the changed set
Exit 0 ONLY if every hard check passes. Prints a receipt table for banking.
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

PINNED_BASE = "71e20414b375b7ac4db46817fd68a9c4c45599d3"
BRANCH = "flauz-tlb/dh-gap6a-bgux"
FLAUZ_CLONE = "/home/z/flauz"
INSTRUMENTS = [
    "extensions/flauz-agent/core/orchStore.mjs",
    "extensions/flauz-agent/core/a2a.mjs",
    "extensions/flauz-agent/core/orchestration.mjs",
    "build/flauz/capabilities/background-agent/common/launch.ts",
    "build/flauz/capabilities/background-agent/common/inspect.ts",
    "build/flauz/capabilities/background-agent/common/message.ts",
    "build/flauz/capabilities/background-agent/common/control.ts",
    "build/flauz/capabilities/background-agent/common/outcome.ts",
    "build/flauz/capabilities/background-agent/common/registryView.ts",
    "build/flauz/zcode-patterns/common/backgroundAgent.ts",
    "build/flauz/zcode-patterns/common/hooks.ts",
    "build/flauz/zcode-patterns/common/memoryProjection.ts",
    "build/flauz/zcode-patterns/common/planContinuity.ts",
    "build/flauz/zcode-patterns/common/replayResume.ts",
    "build/flauz/zcode-patterns/common/runHealth.ts",
]
SHA_RE = re.compile(r"\b([0-9a-f]{64})\b")
HEX40_RE = re.compile(r"\b([0-9a-f]{40})\b")


def run(cmd, cwd=None, timeout=120):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def blob_sha256(repo, ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"],
                       capture_output=True, cwd=repo, timeout=120)
    if r.returncode != 0:
        return None
    return hashlib.sha256(r.stdout).hexdigest()


def parse_manifest(text):
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
        path = re.sub(r"^[-\u2013\u2014|:\s]+", "", path).strip()
        path = path.strip("`\"'").strip()
        if not path or path.startswith("#"):
            continue
        if HEX40_RE.fullmatch(path) or " " in path:
            toks = [t for t in re.split(r"[\s|]+", rest) if t]
            cand = [t for t in toks if not HEX40_RE.fullmatch(t) and ("/" in t or t.count(".") >= 1)]
            if not cand:
                continue
            path = cand[0].strip("`\"'*:,-")
        rows.append((sha, path))
    return rows, tree_check


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base_arg = None
    if "--base" in sys.argv:
        i = sys.argv.index("--base")
        if i + 1 < len(sys.argv):
            m = HEX40_RE.fullmatch(sys.argv[i + 1].strip())
            if m:
                base_arg = m.group(1)
    if len(args) < 2:
        print(__doc__)
        return 2
    man_path = os.path.abspath(args[0])
    bundle_dir = os.path.abspath(args[1])
    bundle = os.path.join(bundle_dir, "gap6a-bgux.bundle")
    if not os.path.exists(man_path):
        print(f"FAIL: MANIFEST not found: {man_path}")
        return 2
    if not os.path.exists(bundle):
        print(f"FAIL: bundle not found: {bundle}")
        return 2

    text = open(man_path, encoding="utf-8", errors="replace").read()
    rows, tree_check = parse_manifest(text)
    print(f"manifest rows parsed: {len(rows)}; TREE-SELF-CHECK: {'present' if tree_check else 'MISSING'}")
    if base_arg and base_arg != PINNED_BASE:
        print(f"declared BASE (rebase): {base_arg} (pinned was {PINNED_BASE[:12]})")

    receipts = []
    ok = True

    def bank(check, verdict, detail=""):
        nonlocal ok
        if not verdict:
            ok = False
        receipts.append((check, "PASS" if verdict else "FAIL", detail))

    with tempfile.TemporaryDirectory(prefix="gap6a-verify-") as repo:
        run(["git", "init", "-q", repo])
        # 1. bundle ref surface
        rc, out, err = run(["git", "bundle", "list-heads", bundle], cwd=repo)
        heads = [l.split()[1] for l in out.splitlines() if l.strip()]
        bank("bundle single ref == flauz-tlb/dh-gap6a-bgux",
             heads == [f"refs/heads/{BRANCH}"], f"heads={heads}")
        # fetch the branch from the bundle (thin or full)
        rc, out, err = run(["git", "fetch", "-q", bundle, f"{BRANCH}:refs/heads/wt"], cwd=repo)
        bank("bundle fetch", rc == 0, err[:160])
        if rc != 0:
            _print_receipts(receipts)
            return 1
        # 2. single commit + parent == BASE
        rc, out, err = run(["git", "rev-list", "--count", "wt"], cwd=repo)
        # (thin bundle: count vs parent)
        rc2, parent, _ = run(["git", "rev-parse", "wt^"], cwd=repo)
        rc3, head, _ = run(["git", "rev-parse", "wt"], cwd=repo)
        declared = base_arg or PINNED_BASE
        bank("single commit on the branch (parent is the declared BASE)",
             rc2 == 0 and parent == declared,
             f"parent={parent[:12] if rc2 == 0 else 'none'} declared={declared[:12]}")
        # the rebase honesty check: the declared base must be a REAL main
        # ancestor (witnessed by the local flauz clone, origin/main)
        if os.path.isdir(os.path.join(FLAUZ_CLONE, ".git")):
            rcA, _, errA = run(["git", "merge-base", "--is-ancestor",
                                declared, "origin/main"], cwd=FLAUZ_CLONE)
            bank("declared BASE is an ancestor of origin/main (real tip)",
                 rcA == 0, errA[:120])
        else:
            bank("declared BASE is an ancestor of origin/main (real tip)",
                 False, "no local flauz clone witness")
        # 3. every manifest row: sha at branch head
        bad = [p for sha, p in rows if blob_sha256(repo, "wt", p) != sha]
        bank(f"every MANIFEST row sha256 matches at branch head ({len(rows)} rows)",
             not bad, f"mismatches={bad[:4]}")
        # 4. changed set == manifest set (both ways)
        rc, diff, _ = run(["git", "diff", "--name-only", f"{declared}", "wt"], cwd=repo)
        changed = set(l for l in diff.splitlines() if l.strip())
        manifest_set = set(p for _s, p in rows)
        bank("changed-file set == MANIFEST set (both ways)",
             changed == manifest_set,
             f"only-in-diff={sorted(changed - manifest_set)[:4]} only-in-manifest={sorted(manifest_set - changed)[:4]}")
        # 5. TREE-SELF-CHECK
        rc, wt_hash, _ = run(["git", "rev-parse", "wt^{tree}"], cwd=repo)
        if tree_check and rc == 0:
            h = wt_hash.strip()
            bank("TREE-SELF-CHECK matches the branch tree hash",
                 tree_check in (h, hashlib.sha256(h.encode()).hexdigest()),
                 f"tree={h[:12]} manifest={tree_check[:12]}")
        else:
            bank("TREE-SELF-CHECK present + tree resolvable",
                 bool(tree_check) and rc == 0, "")
        # 6. THE FROZEN-15 LAW
        frozen_bad = []
        for path in INSTRUMENTS:
            b1 = blob_sha256(repo, declared, path)
            b2 = blob_sha256(repo, "wt", path)
            if b1 is None or b2 is None or b1 != b2 or path in changed:
                frozen_bad.append(path)
        bank(f"the FROZEN-15 byte-identical BASE<->branch + untouched ({len(INSTRUMENTS)} files)",
             not frozen_bad, f"violations={frozen_bad[:4]}")

    _print_receipts(receipts)
    return 0 if ok else 1


def _print_receipts(receipts):
    print("\n=== GAP-6A VERIFY RECEIPTS ===")
    for check, verdict, detail in receipts:
        line = f"  [{verdict}] {check}"
        if detail:
            line += f"  ({detail})"
        print(line)
    allpass = all(v == "PASS" for _c, v, _d in receipts)
    print(f"=== RESULT: {'ALL-PASS' if allpass else 'VERIFY-FAIL'} ===")


if __name__ == "__main__":
    raise SystemExit(main())
