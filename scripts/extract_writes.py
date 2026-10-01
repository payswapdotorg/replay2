#!/usr/bin/env python3
"""extract_writes.py — recover a worker's full file-surface from the batch store.

§10b doctrine (AGENT_BOOT_PROMPT): the session narrative (server-side batch
store) is the PRIMARY delivery artifact — every Write/Edit/MultiEdit tool
call is recorded verbatim in content_blocks (type tool_calls, array items
{function:{name, arguments}} with arguments.filepath + arguments.content).
Pods get recycled mid-delivery; the narrative survives.

This tool:
  1. resolves the chat id (registry session name OR raw uuid),
  2. dumps ALL messages from the batch store (id list from the chat record,
     refreshed for in-flight turns),
  3. extracts every file-tool call in TIME order — sort by (message ts,
     block started_at, block index, call index); NEVER trust Object.keys
     order of the batch data map (insertion-random),
  4. emits an output directory with:
       manifest.json  — every op (kind, filepath, sizes, sha256, results)
       files/<n>-<basename> — full content for Write ops (and Edit results
                        snapshots when present in tool results)
       bash_log.json  — every Bash tool call (command + result head)
  5. prints a per-file assembly plan for replay_lane.py.

Usage: extract_writes.py <session-name-or-chat-uuid> <outdir>
Exit: 0 = at least one file op extracted; 1 = none / unreadable chat.
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
TOKEN_CACHE = os.path.join(FLAGS, "chat_token")
API = "https://chat.z.ai"


def _token():
    try:
        return open(TOKEN_CACHE).read().strip()
    except Exception:
        return ""


def _api(path, method="GET", body=None):
    req = urllib.request.Request(API + path, method=method,
        headers={"Authorization": "Bearer " + _token(),
                 "Content-Type": "application/json"})
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data, timeout=60) as r:
        return json.loads(r.read().decode())


def _resolve_chat(name):
    """Session name -> chat uuid via the registry; raw uuid passes through."""
    if re.match(r"^[0-9a-f-]{36}$", name):
        return name
    reg = os.path.join(FLAGS, "session_registry.jsonl")
    if os.path.isfile(reg):
        best = None
        for line in open(reg, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("name") == name and rec.get("url"):
                best = rec  # last record wins (re-aims update tab/url)
        if best:
            cid = (best.get("url") or "").split("/c/")[-1].split("/")[0].split("?")[0]
            if len(cid) >= 30:
                return cid
    raise SystemExit(f"cannot resolve session {name!r} to a chat uuid")


def _batch_all(cid):
    """Chat record -> full message list from the batch store.

    The record's history id list can MISS in-flight turns (id-list lag) —
    merge ids from the record AND a live messages view when available."""
    d = _api(f"/api/v1/chats/{cid}")
    h = ((d.get("chat") or {}).get("history")) or {}
    ids = list((h.get("messages") or {}).keys())
    b = _api(f"/api/v1/chats/{cid}/messages/batch", "POST", {"ids": ids})
    data = b.get("data") or {}
    # second pass: some batch payloads reference children ids not in the
    # record yet — fetch those too (bounded)
    extra = set()
    for v in data.values():
        if isinstance(v, dict):
            for c in (v.get("childrenIds") or []):
                if c not in data and c not in ids:
                    extra.add(c)
    if extra:
        b2 = _api(f"/api/v1/chats/{cid}/messages/batch", "POST", {"ids": sorted(extra)})
        data.update(b2.get("data") or {})
    return data


def _block_ts(blk):
    return blk.get("started_at") or blk.get("created_at") or 0


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    name, outdir = sys.argv[1], sys.argv[2]
    cid = _resolve_chat(name)
    print(f"chat {cid}")
    data = _batch_all(cid)
    os.makedirs(os.path.join(outdir, "files"), exist_ok=True)

    ops = []          # file-tool ops in time order
    bash_calls = []   # bash log
    reports = []      # large assistant text blocks (candidate reports)

    for mid, m in data.items():
        if not isinstance(m, dict):
            continue
        mts = m.get("ts") or m.get("timestamp") or 0
        blocks = m.get("content_blocks") or []
        for bi, blk in enumerate(blocks):
            if not isinstance(blk, dict):
                continue
            bts = _block_ts(blk)
            if blk.get("type") == "tool_calls":
                for ci, call in enumerate(blk.get("content") or []):
                    if not isinstance(call, dict):
                        continue
                    fn = (call.get("function") or {})
                    fname = fn.get("name") or ""
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except Exception:
                        args = {}
                    results = call.get("results") or []
                    rtext = ""
                    for rr in results:
                        if isinstance(rr, dict):
                            rtext += str(rr.get("content") or "")
                        elif isinstance(rr, str):
                            rtext += rr
                    entry = {
                        "seq": len(ops) + len(bash_calls),
                        "msg": mid, "msg_ts": mts, "block": bi, "call": ci,
                        "block_ts": bts, "role": m.get("role"),
                        "tool": fname, "args": args,
                        "result_head": rtext[:400],
                        "result_len": len(rtext),
                    }
                    if fname in ("Write", "write_file", "write-file", "create_file"):
                        entry["kind"] = "write"
                        entry["filepath"] = args.get("filepath") or args.get("path") or args.get("file_path") or ""
                        content = args.get("content") or ""
                        entry["chars"] = len(content)
                        entry["sha256"] = hashlib.sha256(content.encode()).hexdigest()[:16]
                        ops.append(entry)
                    elif fname in ("Edit", "edit_file", "edit-file"):
                        entry["kind"] = "edit"
                        entry["filepath"] = args.get("filepath") or args.get("path") or args.get("file_path") or ""
                        entry["old_chars"] = len(args.get("old_str") or args.get("old_string") or "")
                        entry["new_chars"] = len(args.get("new_str") or args.get("new_string") or "")
                        ops.append(entry)
                    elif fname in ("MultiEdit", "multi_edit", "multi-edit"):
                        entry["kind"] = "multiedit"
                        entry["filepath"] = args.get("filepath") or args.get("path") or args.get("file_path") or ""
                        entry["edits"] = len(args.get("edits") or [])
                        ops.append(entry)
                    elif fname in ("Bash", "bash", "shell", "execute_command"):
                        entry["kind"] = "bash"
                        entry["command"] = (args.get("command") or "")[:300]
                        bash_calls.append(entry)
            elif blk.get("type") == "text" and m.get("role") == "assistant":
                txt = str(blk.get("content") or "")
                if len(txt) > 1500:
                    reports.append({"msg": mid, "chars": len(txt),
                                    "head": txt[:200], "ts": mts})

    # time order
    def _k(e):
        return (e.get("msg_ts") or 0, e.get("block_ts") or 0, e.get("block", 0), e.get("call", 0))
    ops.sort(key=_k)
    bash_calls.sort(key=_k)

    # write files for Write ops
    fn = 0
    for e in ops:
        if e["kind"] == "write":
            content = e["args"].get("content") or ""
            fn += 1
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", e["filepath"].strip("/").replace("/", "__"))[-100:]
            path = os.path.join(outdir, "files", f"{fn:04d}-{safe}")
            open(path, "w", encoding="utf-8").write(content)
            e["staged_file"] = os.path.relpath(path, outdir)

    manifest = {
        "chat_id": cid, "extracted_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ"),
        # args stay in the manifest for edit/multiedit (old_str/new_str are the
        # payload replay_lane needs); Write content lives in files/ (staged_file)
        "file_ops": ops,
        "bash_calls": bash_calls,
        "large_texts": reports,
    }
    open(os.path.join(outdir, "manifest.json"), "w").write(json.dumps(manifest, indent=1))
    open(os.path.join(outdir, "bash_log.json"), "w").write(
        json.dumps([{ "cmd": b.get("command"), "result_head": b.get("result_head"),
                      "ts": b.get("msg_ts")} for b in bash_calls], indent=1))

    # assembly plan
    byfile = {}
    for e in ops:
        byfile.setdefault(e["filepath"], []).append(f"{e['kind']}#{e['seq']}")
    print(f"file ops: {len(ops)} (write={sum(1 for e in ops if e['kind']=='write')}, "
          f"edit={sum(1 for e in ops if e['kind']=='edit')}, "
          f"multiedit={sum(1 for e in ops if e['kind']=='multiedit')}); bash: {len(bash_calls)}")
    for f, kinds in sorted(byfile.items()):
        print(f"  {f}  [{', '.join(kinds)}]")
    return 0 if ops or reports else 1


if __name__ == "__main__":
    sys.exit(main())
