#!/usr/bin/env python3
"""worklog_harvest.py — reconstruct a worker's delivery from its work log.

2026-09-21 context (prod024): the packet's delivery protocol drifted (no
delivery/-staging step), so the worker committed its branch inside its
sandbox clone (/home/z/AISE) which the workspaces files API CANNOT serve
(the API's ../<name>/ paths are virtual-project aliases, not traversal —
verified byte-identical to the project root). The clone is unreachable.

But the batch store holds the worker's FULL work log — every tool call
with complete arguments. All-new-file deliveries (0 deletions) can be
reconstructed losslessly from:

  1. Write tool calls  -> {filepath, content}
  2. Bash heredocs     -> cat > path << 'MARKER' ... MARKER
  3. Bash echo/printf  -> single-line file writes (DELIVERY.txt etc.)

Output: harvests/<name>-delivery/ with the reconstructed tree + a
manifest of what was recovered. Verification (diffstat-exact vs base,
verify re-run) is the Lead's gate, done at the integration station.

Usage: worklog_harvest.py <session-name> <assistant-message.json>
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def extract_write_calls(blocks):
    """Write tool calls: full file contents."""
    files = {}
    for b in blocks:
        if b.get("type") != "tool_calls":
            continue
        for tc in (b.get("content") or []):
            fn = (tc.get("function") or {})
            if fn.get("name") != "Write":
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                continue
            fp, content = args.get("filepath"), args.get("content")
            if fp and content is not None:
                files[fp] = content
    return files


HEREDOC_RE = re.compile(
    r"(?:cat|tee)\s+>?\s*'([^']+)'\s*<<\s*'([A-Za-z_0-9]+)'\n(.*?)\n\2",
    re.S)


def extract_heredocs(blocks):
    """Bash heredoc writes: cat > path << 'MARKER' ... MARKER."""
    files = {}
    for b in blocks:
        if b.get("type") != "tool_calls":
            continue
        for tc in (b.get("content") or []):
            fn = (tc.get("function") or {})
            if fn.get("name") != "Bash":
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                continue
            cmd = args.get("command") or ""
            for m in HEREDOC_RE.finditer(cmd):
                path, body = m.group(1), m.group(3)
                files[path] = body + "\n"
    return files


ECHO_RE = re.compile(
    r"(?:echo|printf)(?:\s+-e)?\s+'([^']*)'\s*>\s*'([^']+)'")


def extract_echo_writes(blocks):
    """Single-line echo/printf writes (manifests, markers)."""
    files = {}
    for b in blocks:
        if b.get("type") != "tool_calls":
            continue
        for tc in (b.get("content") or []):
            fn = (tc.get("function") or {})
            if fn.get("name") != "Bash":
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                continue
            cmd = args.get("command") or ""
            for m in ECHO_RE.finditer(cmd):
                body, path = m.group(1), m.group(2)
                files[path] = body + "\n"
    return files


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    name, msg_file = sys.argv[1], sys.argv[2]
    msg = json.load(open(msg_file))
    blocks = msg.get("content_blocks") or []

    writes = extract_write_calls(blocks)
    heredocs = extract_heredocs(blocks)
    echoes = extract_echo_writes(blocks)

    # precedence: Write tool > heredoc > echo; last occurrence wins within a kind
    all_files = {}
    all_files.update(echoes)
    all_files.update(heredocs)
    all_files.update(writes)

    out = os.path.join(BASE, "harvests", f"{name}-delivery")
    os.makedirs(out, exist_ok=True)
    repo_prefix = None
    # normalize: strip a common repo prefix (e.g. /home/z/AISE/)
    prefixes = {}
    for fp in all_files:
        head = "/".join(fp.split("/")[:3]) + "/" if fp.startswith("/") else None
        if head:
            prefixes[head] = prefixes.get(head, 0) + 1
    if prefixes:
        repo_prefix = max(prefixes, key=prefixes.get)

    manifest = []
    for fp, content in sorted(all_files.items()):
        rel = fp
        if repo_prefix and fp.startswith(repo_prefix):
            rel = fp[len(repo_prefix):]
        elif fp.startswith("/"):
            rel = fp.lstrip("/")
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        manifest.append({"path": rel, "chars": len(content),
                         "source": "write" if fp in writes
                         else ("heredoc" if fp in heredocs else "echo")})

    with open(os.path.join(out, "_RECOVERY_MANIFEST.json"), "w") as f:
        json.dump({"files": manifest, "repo_prefix": repo_prefix,
                   "counts": {"write": len(writes), "heredoc": len(heredocs),
                              "echo": len(echoes), "total": len(all_files)}},
                  f, indent=1)

    print(f"Write calls: {len(writes)} | heredoc writes: {len(heredocs)} | "
          f"echo writes: {len(echoes)}")
    print(f"reconstructed files: {len(all_files)} -> {out}")
    print(f"repo prefix: {repo_prefix}")
    by_top = {}
    for m in manifest:
        top = m["path"].split("/")[0]
        by_top[top] = by_top.get(top, 0) + 1
    print("by top dir:", json.dumps(by_top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
