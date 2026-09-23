#!/usr/bin/env python3
"""harvest_pod_commit.py <name> <chat-uuid> <workspace-id> [out-root]

Reconstruct a worker's git commit from their pod's .git loose objects,
BIT-PERFECT, into a local repo (out-root/<name>-pod/repo, default
/home/z/leads-harvest). The pod's workspace files API serves raw bytes for
any path — including .git/objects/* (ls-tree hides .git but path reads
work). We read HEAD -> ref -> commit sha, then materialize every object the
local station clone does NOT already have (delta-only fetches), rebuild the
commit with the exact tree/author/committer/dates/message, and verify the
resulting sha equals the pod's sha.

REBUILD NOTE (2026-09-23): original tool lost in sandbox wipe #3; rebuilt
from the Task-86h worklog record which documents 4 fixed bugs:
  (1) the files/content response is sometimes BARE BINARY (no JSON envelope)
      -> capture all parse exceptions, fall back to raw bytes;
  (2) tree objects carry a 'tree NNN\\0' header -> parse_tree strips it;
  (3) native tree dir mode is '40000' (5 chars), not '040000';
  (4) hash-object verification needs the 'blob NNN\\0' header stripped.
First live use after a rebuild may surface new quirks — keep the fallbacks.
"""
import json
import os
import re
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

OUTROOT_DEFAULT = "/home/z/leads-harvest"
STATION = "/home/z/roamlink-station"

FETCH_JS = """(async () => {
  const r = await fetch('/api/v1/web-dev/workspaces/files/content', {
    method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({chatId: __CHAT__, workspace_id: __WS__, rev: 'latest', filepath: __FP__})
  });
  if (!r.ok) return JSON.stringify({error: (await r.text()).slice(0, 300)});
  const buf = await r.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let text = null;
  try { text = new TextDecoder('utf-8', {fatal: true}).decode(bytes); } catch (e) {}
  if (text !== null && !bytes.includes(0)) return JSON.stringify({text: text});
  let bin = '';
  const CH = 65536;
  for (let i = 0; i < bytes.length; i += CH) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return JSON.stringify({b64: btoa(bin), size: bytes.length});
})()"""


def pick_tab():
    """Wedge-proof chat.z.ai tab selection (2026-09-15 doctrine)."""
    for t in channel.list_tabs():
        if "chat.z.ai" not in (t.get("url") or ""):
            continue
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=20)
            c.eval("1+1", await_promise=False, timeout=8)
            return c
        except Exception:
            try:
                c.close()
            except Exception:
                pass
    raise SystemExit("no responsive chat.z.ai tab for harvest")


def fetch_bytes(cdp, chat_raw, ws_id, filepath):
    """Fetch one file's raw bytes. Handles JSON envelope AND bare-binary
    responses (bug 1: any parse failure falls back to raw)."""
    js = FETCH_JS.replace("__CHAT__", json.dumps(chat_raw)) \
                 .replace("__WS__", json.dumps(ws_id)) \
                 .replace("__FP__", json.dumps(filepath))
    result = cdp.eval(js, await_promise=True, timeout=60)
    if not isinstance(result, str) or not result:
        raise RuntimeError(f"empty response for {filepath}")
    try:
        envelope = json.loads(result)
        if isinstance(envelope, dict):
            if "error" in envelope:
                raise RuntimeError(f"api error for {filepath}: {envelope['error']!r}")
            if "b64" in envelope:
                import base64
                return base64.b64decode(envelope["b64"])
            if "text" in envelope:
                return envelope["text"].encode("utf-8", "surrogateescape")
    except (json.JSONDecodeError, ValueError):
        pass  # fall through to raw
    except Exception:
        pass  # bug-1 doctrine: ANY envelope failure -> raw fallback
    # bare binary (the eval string may carry latin-1-mangled bytes)
    return result.encode("latin-1", "replace")


def fetch_text(cdp, chat_raw, ws_id, filepath):
    return fetch_bytes(cdp, chat_raw, ws_id, filepath).decode("utf-8", "replace").strip()


# --------------------------------------------------------------- git object --

def object_path(sha):
    return f".git/objects/{sha[:2]}/{sha[2:]}"


def fetch_zlib_object(cdp, chat_raw, ws_id, sha):
    raw = fetch_bytes(cdp, chat_raw, ws_id, object_path(sha))
    try:
        return zlib.decompress(raw)
    except zlib.error as e:
        raise RuntimeError(f"object {sha} not zlib (packed? corrupt?): {e}")


def split_object_header(decompressed):
    """'tree 123\\0<content>' -> ('tree', content)."""
    nul = decompressed.index(b"\x00")
    header = decompressed[:nul].decode("ascii", "replace")
    otype, _, size = header.partition(" ")
    return otype, decompressed[nul + 1:]


def parse_tree(tree_content):
    """Native tree entries: '<mode> <name>\\0<20-byte sha>'. Dir mode is
    '40000' (5 chars, bug 3). Returns [(mode, name, hexsha)]."""
    entries = []
    i = 0
    while i < len(tree_content):
        sp = tree_content.index(b" ", i)
        mode = tree_content[i:sp].decode("ascii")
        nul = tree_content.index(b"\x00", sp)
        name = tree_content[sp + 1:nul].decode("utf-8", "surrogateescape")
        sha = tree_content[nul + 1:nul + 21].hex()
        entries.append((mode, name, sha))
        i = nul + 21
    return entries


def parse_commit(commit_content):
    """Commit object content -> dict(tree, parents[], author, committer,
    message) with raw identity lines preserved for the replay."""
    head, _, message = commit_content.partition(b"\n\n")
    fields = {"parents": []}
    for line in head.decode("utf-8", "replace").split("\n"):
        if line.startswith("tree "):
            fields["tree"] = line[5:].strip()
        elif line.startswith("parent "):
            fields["parents"].append(line[7:].strip())
        elif line.startswith("author "):
            fields["author_line"] = line[7:]
        elif line.startswith("committer "):
            fields["committer_line"] = line[10:]
    fields["message"] = message.decode("utf-8", "surrogateescape")
    return fields


IDENT_RE = re.compile(r"^(.*?) <(.*?)> (\d+) ([+-]\d{4})$")


def ident_env(prefix, line):
    m = IDENT_RE.match(line)
    if not m:
        raise RuntimeError(f"unparseable identity line: {line!r}")
    name, email, ts, tz = m.groups()
    return {
        f"GIT_{prefix}_NAME": name,
        f"GIT_{prefix}_EMAIL": email,
        f"GIT_{prefix}_DATE": f"{ts} {tz}",
    }


# ------------------------------------------------------------ local repo ops --

def git(repo, *args, stdin=None, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(["git", "-C", repo, *args], input=stdin,
                       capture_output=True, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.decode()[:300]}")
    return p.stdout


def have_object(repo, sha):
    p = subprocess.run(["git", "-C", repo, "cat-file", "-e", sha],
                       capture_output=True)
    return p.returncode == 0


def materialize(cdp, chat_raw, ws_id, repo, sha, expect_type):
    """Delta-materialize one object into the local repo (skip if present)."""
    if have_object(repo, sha):
        return
    decompressed = fetch_zlib_object(cdp, chat_raw, ws_id, sha)
    otype, content = split_object_header(decompressed)
    if otype != expect_type:
        raise RuntimeError(f"object {sha}: expected {expect_type}, got {otype}")
    if otype == "tree":
        for mode, name, esha in parse_tree(content):
            materialize(cdp, chat_raw, ws_id, repo, esha,
                        "tree" if mode.startswith("4") else "blob")
    # bug 4: write CONTENT only (header stripped); hash-object adds its own
    out = git(repo, "hash-object", "-w", "-t", otype, "--stdin", stdin=content)
    got = out.decode().strip()
    if got != sha:
        raise RuntimeError(f"hash mismatch for {sha}: hash-object gave {got}")


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    name, chat_uuid, ws_id = sys.argv[1], sys.argv[2], sys.argv[3]
    out_root = sys.argv[4] if len(sys.argv) > 4 else OUTROOT_DEFAULT
    chat_raw = chat_uuid.removeprefix("chat-")

    # 1. read the pod's HEAD -> branch -> commit sha (loose refs; fresh
    #    worker commits are never packed yet)
    cdp = pick_tab()
    try:
        head = fetch_text(cdp, chat_raw, ws_id, ".git/HEAD")
        m = re.match(r"ref: refs/heads/(.+)", head)
        if not m:
            raise SystemExit(f"detached HEAD in pod: {head!r}")
        branch = m.group(1).strip()
        ref_sha = fetch_text(cdp, chat_raw, ws_id, f".git/refs/heads/{branch}")
        if not re.fullmatch(r"[0-9a-f]{40}", ref_sha):
            # loose ref missing -> reflog tail fallback
            log = fetch_text(cdp, chat_raw, ws_id, ".git/logs/HEAD")
            ref_sha = log.strip().split("\n")[-1].split(" ")[1]
        print(f"pod HEAD: {branch} @ {ref_sha}")

        # 2. read + parse the commit object
        commit_raw = fetch_zlib_object(cdp, chat_raw, ws_id, ref_sha)
        ctype, commit_content = split_object_header(commit_raw)
        if ctype != "commit":
            raise SystemExit(f"HEAD object is a {ctype}, not a commit")
        c = parse_commit(commit_content)
        print(f"commit: tree {c['tree'][:12]} parents {len(c['parents'])} "
              f"author {c['author_line'][:40]}...")
        print(f"message: {c['message'].splitlines()[0][:100] if c['message'] else '(empty)'}")

        # 3. local out repo = clone of the station (has the parent history)
        out_repo = os.path.join(out_root, f"{name}-pod", "repo")
        if not os.path.isdir(os.path.join(out_repo, ".git")):
            subprocess.run(["git", "clone", "--quiet", STATION, out_repo], check=True)
        for parent in c["parents"]:
            if not have_object(out_repo, parent):
                raise SystemExit(f"parent {parent} missing in station clone — "
                                 f"update the station first (git fetch)")

        # 4. delta-materialize the tree (blobs + subtrees not already local)
        materialize(cdp, chat_raw, ws_id, out_repo, c["tree"], "tree")

        # 5. rebuild the commit bit-perfect
        env = {}
        env.update(ident_env("AUTHOR", c["author_line"]))
        env.update(ident_env("COMMITTER", c["committer_line"]))
        args = ["commit-tree", c["tree"]]
        for parent in c["parents"]:
            args += ["-p", parent]
        new_sha = git(out_repo, *args, stdin=c["message"].encode(),
                      env_extra=env).decode().strip()
        if new_sha != ref_sha:
            raise SystemExit(f"MISMATCH: replay gave {new_sha}, pod has {ref_sha}")
        git(out_repo, "update-ref", f"refs/heads/{branch}", new_sha)
        git(out_repo, "checkout", "--quiet", branch)
        print(f"BIT-PERFECT: {new_sha} == pod {ref_sha} on branch {branch}")
        print(f"out repo: {out_repo}")
    finally:
        try:
            cdp.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
