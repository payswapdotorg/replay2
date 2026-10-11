#!/usr/bin/env python3
"""tl_replay.py <harvest.json> <station-root> [--only <subtree>] [--dry] — §10b replay.

TRUE time-ordered replay: Write/Edit/MultiEdit tool ops and ===FILE:===
envelopes are interleaved by (ts, sequence). Within one message: tool ops
first (in block/call order), then envelopes (chat emission follows tool use).
Last state per file wins. Handles the 'mv' rename for journal.ts.test.ts.
"""
import json
import re
import shlex
import sys
import os

REDIRECT_RE = re.compile(r"^(>>?)$")
HEAD_N_RE = re.compile(r"^-(\d+)$")
SED_RANGE_RE = re.compile(r"^'?(\d+),(\d+)p'?$")
PY_HEREDOC_RE = re.compile(r"python3?\s+(?:-\s+)?<<\s*'([A-Za-z_][A-Za-z0-9_]*)'\n(.*?)\n\1(?:\n|$)", re.S)
CD_PREFIX_RE = re.compile(r"^\s*cd\s+(\S+)\s*&&")
NODE_SIG_RE = re.compile(r"\bnode\s+(?:-e|--eval)\s")

# JS virtual-fs wrapper for node -e replay (PL-033 doctrine). The worker's
# recorded `node -e "..."` bodies are deterministic fs mutations
# (readFileSync/writeFileSync string surgery). We execute them with a REAL
# node subprocess whose fs module is shimmed onto the in-memory tree — no
# real station IO; foreign-path writes are dropped (station-root prefixes
# normalize; /tmp etc. return null -> writeFileSync no-ops).
_NODE_WRAPPER = r'''"use strict";
const __vfs = %s;
const __cwd = %s;
const __realfs = require('fs');
const __roots = ['/home/z/my-project/PlayLiquid/', '/home/z/my-project/playliquid/', '/home/z/PlayLiquid/', '/home/z/playliquid/', '/home/z/my-project/', '/home/z/'];
function __rel(p) {
  p = String(p);
  if (p.startsWith('/')) {
    for (const r of __roots) {
      if (p === r.slice(0, -1)) return '';           // the station root itself
      if (p.startsWith(r)) return p.slice(r.length);  // station-relative
    }
    return null;                                     // foreign absolute
  }
  const parts = [];
  for (const s of (__cwd ? __cwd + '/' + p : p).split('/')) {
    if (!s || s === '.') continue;
    if (s === '..') { parts.pop(); continue; }
    parts.push(s);
  }
  return parts.join('/');
}
const __shim = Object.create(__realfs);
__shim.readFileSync = function (p, o) {
  const r = __rel(p);
  if (r === null) { try { return __realfs.readFileSync(p, o); } catch (e) { return ''; } }
  return r in __vfs ? __vfs[r] : '';
};
__shim.writeFileSync = function (p, d) { const r = __rel(p); if (r !== null) __vfs[r] = String(d); };
__shim.appendFileSync = function (p, d) { const r = __rel(p); if (r !== null) __vfs[r] = (__vfs[r] || '') + String(d); };
__shim.existsSync = function (p) { const r = __rel(p); return r !== null && (r in __vfs); };
__shim.unlinkSync = function (p) { const r = __rel(p); if (r !== null) delete __vfs[r]; };
__shim.rmSync = function (p) { const r = __rel(p); if (r !== null) delete __vfs[r]; };
__shim.mkdirSync = function () {};
__shim.readdirSync = function (p) {
  const r = __rel(p);
  if (r === null) return [];
  const pre = r ? r + '/' : '';
  const out = [];
  for (const k of Object.keys(__vfs)) {
    if (k.startsWith(pre)) out.push(k.slice(pre.length).split('/')[0]);
  }
  return out;
};
__shim.statSync = function (p) {
  const r = __rel(p);
  if (r === null || !(r in __vfs)) { const e = new Error('ENOENT: ' + p); e.code = 'ENOENT'; throw e; }
  return { isFile: () => true, isDirectory: () => false, size: (__vfs[r] || '').length };
};
const __Module = require('module');
const __origLoad = __Module._load;
__Module._load = function (request, parent, isMain) {
  if (request === 'fs') return __shim;
  return __origLoad.apply(this, arguments);
};
// DUMP-VIA-FILE + EXIT-HOOK (PL-033 field lesson: a stdout-pipe dump races
// the process exit — node can exit before the pipe drains, truncating the
// JSON mid-string). The exit hook fires on normal exit, process.exit() AND
// uncaught-exception paths; writeFileSync is synchronous and atomic-enough
// for a single writer.
const __DUMPPATH = %s;
process.on('exit', function () {
  try { __realfs.writeFileSync(__DUMPPATH, JSON.stringify(__vfs)); } catch (e) {}
});
try {
%s
} catch (e) { /* worker-side failure semantics: partial writes stand */ }
'''


def _run_node_eval(code, cwd, files, timeout=25):
    """Execute a recorded `node -e` body against the in-memory tree.

    Returns (status, files_dict_after, note) with status in
    ('ok', 'skip', 'fail'). The wrapper shims fs to the in-memory tree; an
    exit hook dumps the final virtual tree to a file (no stdout race).
    Nonzero exit still merges back: node -e is sequential, so partial
    writes match the worker's real semantics."""
    import subprocess
    import tempfile
    if "process.stdin" in code:
        # stdin-dependent op (agent-browser pipelines): the recorded body
        # consumes a live stream we cannot reproduce — advisory skip.
        return "skip", files, "stdin-dependent"
    files = dict(files)  # snapshot: failures must not corrupt the tree
    dump = tempfile.mktemp(suffix=".plvfs.json")
    # %% escaping: user JS freely contains % (template literals, remainders);
    # the % operator would misread them as placeholders. Substituted VALUES
    # are never re-formatted, so only the user-code slot needs escaping.
    wrapper = _NODE_WRAPPER % (json.dumps(files), json.dumps(cwd or ""),
                               json.dumps(dump), code.replace("%", "%%"))
    fd, wpath = tempfile.mkstemp(suffix=".cjs")
    os.close(fd)
    try:
        with open(wpath, "w") as f:
            f.write(wrapper)
        try:
            subprocess.run(["node", wpath], capture_output=True,
                           text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
            ok_dump = os.path.exists(dump)
        except subprocess.TimeoutExpired:
            return "fail", files, "timeout"
        if not ok_dump:
            return "fail", files, "no-dump"
        try:
            with open(dump) as f:
                newvfs = json.load(f)
        except Exception as ex:  # noqa: BLE001
            return "fail", files, "bad-dump: " + str(ex)[:100]
        if not isinstance(newvfs, dict) or not all(isinstance(v, str) for v in newvfs.values()):
            return "fail", files, "bad-dump-shape"
        return "ok", newvfs, ""
    finally:
        for p in (wpath, dump):
            try:
                os.unlink(p)
            except OSError:
                pass


def _cwd_norm(tok):
    """Normalize a cd-target token to a station-relative cwd ('' = root).
    Returns None for foreign directories."""
    if not tok:
        return ""
    tok = tok.rstrip("/")
    for r in _STATION_ROOTS:
        if tok == r.rstrip("/"):
            return ""
    return _station_rel(tok, None)


def norm_path(p):
    p = p.replace("\\", "/")
    roots = ["/home/z/my-project/PlayLiquid/", "/home/z/my-project/playliquid/",
             "/home/z/PlayLiquid/", "/home/z/playliquid/", "/home/z/my-project/", "/home/z/"]
    for r in roots:
        if p.startswith(r):
            return p[len(r):].lstrip("/")
    return p.lstrip("/")


_STATION_ROOTS = ["/home/z/my-project/PlayLiquid/", "/home/z/my-project/playliquid/",
                  "/home/z/PlayLiquid/", "/home/z/playliquid/", "/home/z/my-project/", "/home/z/"]


def _station_rel(path, cwd_rel):
    """Resolve a token path to a station-relative path, or None when it
    lives outside the station (foreign absolute like /tmp/...) or escapes."""
    if not path or "\n" in path:
        return None
    p = path.replace("\\", "/")
    if p.startswith("/"):
        for r in _STATION_ROOTS:
            if p.startswith(r):
                p = p[len(r):]
                break
        else:
            return None  # foreign absolute (e.g. /tmp/...)
    elif cwd_rel:
        p = cwd_rel + "/" + p
    parts = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        return None
    return "/".join(parts)


def parse_bash_surgery(cmd):
    """Parse one Bash command into recognized SAFE file mutations.

    Grammar (PL-025 doctrine — the deterministic surgery workers perform
    outside Write/Edit):
      head -N <src> >|>> <dst>      (also head -n N)
      sed -n 'A,Bp' <src> >|>> <dst>
      echo "<lit>" >> <dst>          (append literal line)
      mv <a> <b>  |  cp <a> <b>  |  rm <f>...
    cd <dir> prefixes set the resolution dir. Statements with pipes,
    substitution ($...), heredocs (<<) or foreign paths are skipped and
    counted for review. Returns (mutations, skipped_count).
    """
    # NODE -E EXCEPTION (PL-033 doctrine): `node -e "<js>"` bodies are file
    # mutations we CAN replay (the recorded code is deterministic worker
    # behavior — readFileSync/writeFileSync string surgery). Detected BEFORE
    # the $()/<< guards because JS bodies freely contain $, && and <<.
    if NODE_SIG_RE.search(cmd):
        nm = _extract_node_eval(cmd)
        if nm is not None:
            return [nm], 0
        # extraction failed (unbalanced quotes etc.) — fall through; the
        # guards below will skip-and-count as before
    if "<<" in cmd or "$(" in cmd or "${" in cmd:
        # PYTHON HEREDOC EXCEPTION: `python3 - <<'EOF'` bodies are file
        # mutations we CAN replay (the recorded code is deterministic
        # worker behavior — json load/modify/dump on station files).
        py = PY_HEREDOC_RE.search(cmd)
        if py is None:
            return [], 0
        cwdm = CD_PREFIX_RE.match(cmd)
        cwd_rel = None
        if cwdm:
            cwd_rel = _station_rel(cwdm.group(1), None)
        if not cwd_rel:
            return [], 0  # heredoc outside the station — not replayable
        return [{"op": "python", "code": py.group(2), "cwd": cwd_rel}], 0
    segments = re.split(r"&&|;", cmd)
    cwd_rel = None
    mutations = []
    skipped = 0
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        try:
            toks = shlex.split(seg)
        except ValueError:
            skipped += 1
            continue
        if not toks:
            continue
        if toks[0] == "cd" and len(toks) == 2:
            cwd_rel = _station_rel(toks[1], cwd_rel) or cwd_rel
            continue
        has_rd = any(t == ">" or t == ">>" for t in toks)
        if "|" in toks or any("$" in t for t in toks):
            if has_rd:
                skipped += 1
            continue
        try:
            mut = _match_mutation(toks, cwd_rel)
        except Exception:
            mut = None
        if mut is not None:
            mutations.append(mut)
        elif has_rd and _rd_target_station(toks, cwd_rel):
            skipped += 1
    return mutations, skipped


def _rd_target_station(toks, cwd_rel):
    ti = toks.index(">") if ">" in toks else (toks.index(">>") if ">>" in toks else -1)
    return ti >= 0 and ti + 1 < len(toks) and bool(_station_rel(toks[ti + 1], cwd_rel))


def _extract_node_eval(cmd):
    """Parse `cd <dir> && node -e "<code>"` into a node mutation record.

    shlex first (handles \" escapes and && inside the JS body); a regex
    fallback covers shlex ValueError cases. Returns None when no -e body
    can be extracted or the cd target is foreign (not replayable)."""
    code = None
    try:
        toks = shlex.split(cmd)
        for i in range(len(toks) - 2):
            if toks[i] == "node" and toks[i + 1] in ("-e", "--eval"):
                code = toks[i + 2]
                break
    except ValueError:
        m = re.search(r"\bnode\s+(?:-e|--eval)\s+(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')", cmd, re.S)
        if m:
            code = shlex.split(m.group(1))[0] if m.group(1)[:1] in '"\'' else m.group(1)[1:-1]
    if code is None:
        return None
    cwdm = CD_PREFIX_RE.match(cmd)
    cwd_rel = _cwd_norm(cwdm.group(1)) if cwdm else ""
    if cwd_rel is None:
        return None  # foreign cwd — not replayable
    return {"op": "node", "code": code, "cwd": cwd_rel}


def _match_mutation(toks, cwd_rel):
    """Match ONE recognized statement shape, else None."""
    head = toks[0]
    if head == "mv" and len(toks) == 3 and not toks[1].startswith("-"):
        a, b = _station_rel(toks[1], cwd_rel), _station_rel(toks[2], cwd_rel)
        if a and b:
            return {"op": "mv", "src": a, "dst": b}
    elif head == "cp" and len(toks) == 3 and not toks[1].startswith("-"):
        a, b = _station_rel(toks[1], cwd_rel), _station_rel(toks[2], cwd_rel)
        if a and b:
            return {"op": "cp", "src": a, "dst": b}
    elif head == "rm" and len(toks) >= 2 and not toks[1].startswith("-"):
        targets = [r for t in toks[1:] if (r := _station_rel(t, cwd_rel))]
        if targets:
            return {"op": "rm", "targets": targets}
    elif head == "head":
        n, i = None, 1
        if i < len(toks) and toks[i] == "-n" and i + 1 < len(toks) and toks[i + 1].isdigit():
            n, i = int(toks[i + 1]), i + 2
        elif i < len(toks) and HEAD_N_RE.match(toks[i]):
            n, i = int(HEAD_N_RE.match(toks[i]).group(1)), i + 1
        if n is not None and i + 3 == len(toks) and REDIRECT_RE.match(toks[i + 1]):
            src, dst = _station_rel(toks[i], cwd_rel), _station_rel(toks[i + 2], cwd_rel)
            if src and dst:
                return {"op": "head", "src": src, "dst": dst, "n": n,
                        "append": toks[i + 1] == ">>"}
    elif head == "sed" and len(toks) == 6 and toks[1] == "-n":
        m = SED_RANGE_RE.match(toks[2])
        if m and REDIRECT_RE.match(toks[4]):
            src, dst = _station_rel(toks[3], cwd_rel), _station_rel(toks[5], cwd_rel)
            if src and dst:
                return {"op": "sed", "src": src, "dst": dst,
                        "a": int(m.group(1)), "b": int(m.group(2)),
                        "append": toks[4] == ">>"}
    elif head == "echo" and len(toks) >= 4 and toks[-2] in (">", ">>"):
        dst = _station_rel(toks[-1], cwd_rel)
        lit = " ".join(toks[1:-2])
        if dst:
            return {"op": "echo", "dst": dst, "lit": lit, "append": toks[-2] == ">>"}
    return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    hj_path, station = sys.argv[1], sys.argv[2]
    bash_skipped = {}
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    lo = 0
    hi = 10**9
    if "--from-order" in sys.argv:
        lo = int(sys.argv[sys.argv.index("--from-order") + 1])
    if "--to-order" in sys.argv:
        hi = int(sys.argv[sys.argv.index("--to-order") + 1])
    dry = "--dry" in sys.argv
    hj = json.load(open(hj_path))

    # build unified op stream
    stream = []  # (ts, seq, kind, payload)
    seq = 0
    write_refused = 0
    for op in hj["ops"]:
        if not (lo <= op["order"] <= hi):
            continue
        tool = op["tool"]
        a = op["args"]
        if tool in ("Write", "write_file", "writeFile", "WriteFile"):
            fp = a.get("filepath") or a.get("path") or a.get("file_path")
            if not fp:
                continue
            res = op.get("result") or ""
            if "can only write files under" in res or "failed to write" in res.lower()[:80]:
                # platform-REFUSED write (PL-033 lesson: /tmp target → "Write
                # tool can only write files under the z user directory") —
                # the file never existed in the worker's pod; replaying it
                # would materialize a phantom tmp/ artifact.
                write_refused += 1
                seq += 1
                continue
            stream.append((op["ts"], seq, "write", norm_path(fp), a.get("content", "")))
        elif tool in ("Edit", "MultiEdit"):
            fp = a.get("filepath") or a.get("path") or a.get("file_path")
            if not fp:
                continue
            rel = norm_path(fp)
            res = op.get("result") or ""
            if tool == "Edit":
                failed = "No replacement was performed" in res
                stream.append((op["ts"], seq, "edit", rel,
                               (a.get("old_str"), a.get("new_str"), bool(a.get("replace_all")), failed)))
            else:
                # Sequential MultiEdit semantics (observed worker behavior,
                # PL-013 op #319 proof): edits apply in order; the first
                # old_str that misses aborts the REMAINING edits of the call
                # but keeps the already-applied ones. So we never pre-fail
                # the whole call; the replay loop enforces the stop.
                for e in a.get("edits", []):
                    stream.append((op["ts"], seq, "edit", rel,
                                   (e.get("old_str"), e.get("new_str"), bool(e.get("replace_all")), False)))
        elif tool == "Bash":
            cmd = a.get("command", "")
            # legacy hard-coded rename (kept for old harvests; the generic
            # parser also catches it — double-apply no-ops since src pops)
            if "mv /home/z/my-project/packages/runtime-core/src/journal.ts.test.ts" in cmd:
                stream.append((op["ts"], seq, "mv",
                               "packages/runtime-core/src/journal.ts.test.ts",
                               "packages/runtime-core/src/journal.test.ts"))
            # generic bash file surgery (PL-025 doctrine): recognized safe
            # mutations interleaved in true op order with writes/edits
            muts, skipped = parse_bash_surgery(cmd)
            for m in muts:
                stream.append((op["ts"], seq, "bashmut", m, None))
            if skipped:
                bash_skipped[seq] = skipped
        seq += 1
    # envelopes: after all ops with the same ts (unless disabled — a range
    # filter usually means a different tree than the envelopes belong to)
    if "--no-envelopes" not in sys.argv:
        for e in hj.get("envelopes", []):
            stream.append((e["ts"], 10**9 + e["order"], "write", e["path"], e["content"]))

    # bash file surgeries (deterministic heredoc mutations the worker performed
    # outside Write/Edit): keyed by op order, applied in stream order
    surgeries = {}
    if "--surgery" in sys.argv:
        surgeries = json.load(open(sys.argv[sys.argv.index("--surgery") + 1]))
        for order, s in surgeries.items():
            stream.append((s.get("_ts", 10**8), int(order), "surgery",
                           s.get("_rel"), (int(order), s)))

    stream.sort(key=lambda s: (s[0], s[1]))

    # apply to in-memory state
    files = {}
    stats = {"write": 0, "edit_ok": 0, "edit_skip_failed": 0, "edit_not_found": 0, "mv": 0,
             "partial_multiedit": 0, "bash_mut": 0}
    if write_refused:
        stats["write_refused"] = write_refused

    def _lines_of(content):
        if not content:
            return []
        return content.split("\n")[:-1] if content.endswith("\n") else content.split("\n")

    def _join_lines(parts):
        return "\n".join(parts) + "\n" if parts else ""
    # group edit stream by originating call so MultiEdit can apply
    # sequentially and STOP at the first failing edit (observed worker
    # semantics: partial application, not atomicity)
    orig_call = {}
    for op in hj["ops"]:
        orig_call[op["order"]] = None
    call_failed = set()
    for item in stream:
        ts, s, kind = item[0], item[1], item[2]
        if kind == "write":
            _, _, _, rel, content = item
            files[rel] = content
            stats["write"] += 1
        elif kind == "edit":
            _, _, _, rel, (old, new, ra, failed) = item
            call_id = item[1]  # seq == op order
            if call_id in call_failed:
                # rest of an aborted MultiEdit call (sequential semantics)
                stats["edit_skip_failed"] += 1
                continue
            if failed:
                # single Edit call the worker reported as not applied
                stats["edit_skip_failed"] += 1
                continue
            cur = files.get(rel)
            if cur is None or old not in cur:
                stats["edit_not_found"] += 1
                # stop applying the REST of this call (sequential semantics)
                call_failed.add(call_id)
                stats["partial_multiedit"] += 1
                continue
            if not ra and cur.count(old) > 1:
                # PL-019 op-118 proof: the chat Edit tool REFUSES an edit
                # whose old_str occurs multiple times (atomic "No
                # replacement was performed") — abort the remaining edits
                # of this call, keeping the already-applied ones.
                stats["edit_multi_occurrence"] = stats.get("edit_multi_occurrence", 0) + 1
                call_failed.add(call_id)
                stats["partial_multiedit"] += 1
                continue
            files[rel] = cur.replace(old, new) if ra else cur.replace(old, new, 1)
            stats["edit_ok"] += 1
        elif kind == "mv":
            _, _, _, src, dst = item
            if src in files:
                files[dst] = files.pop(src)
                stats["mv"] += 1
        elif kind == "bashmut":
            m = item[3]
            op_kind = m["op"]
            if op_kind in ("head", "sed"):
                src_lines = _lines_of(files.get(m["src"], ""))
                if op_kind == "head":
                    frag = src_lines[:m["n"]]
                else:
                    frag = src_lines[m["a"] - 1:m["b"]]
                if m["append"] and m["dst"] in files:
                    files[m["dst"]] += _join_lines(frag)
                else:
                    files[m["dst"]] = _join_lines(frag)
                stats["bash_mut"] += 1
            elif op_kind == "echo":
                lit = m["lit"] + "\n"
                if m["append"] and m["dst"] in files:
                    files[m["dst"]] += lit
                else:
                    files[m["dst"]] = lit
                stats["bash_mut"] += 1
            elif op_kind == "mv":
                if m["src"] in files:
                    files[m["dst"]] = files.pop(m["src"])
                    stats["bash_mut"] += 1
                else:
                    stats.setdefault("bash_mut_src_missing", []).append(m["src"])
            elif op_kind == "cp":
                if m["src"] in files:
                    files[m["dst"]] = files[m["src"]]
                    stats["bash_mut"] += 1
            elif op_kind == "rm":
                for t in m["targets"]:
                    files.pop(t, None)
                stats["bash_mut"] += 1
            elif op_kind == "python":
                # recorded worker heredoc (json load/modify/dump class) —
                # execute against the in-memory tree with a VFile shim so
                # NO real filesystem IO happens (the --surgery precedent)
                cwd = m.get("cwd", "")

                class _VFile:
                    def __init__(self, path, mode="r"):
                        self._rel = (cwd + "/" + path) if cwd else path
                        self._mode = mode
                        if "w" in mode and "a" not in mode and "+" not in mode:
                            files[self._rel] = ""
                        elif "a" in mode and "w" not in mode:
                            files.setdefault(self._rel, "")

                    def read(self, *a):
                        return files.get(self._rel, "")

                    def write(self, data):
                        files[self._rel] = files.get(self._rel, "") + data
                        return len(data)

                    def __iter__(self):
                        return iter(files.get(self._rel, "").splitlines(True))

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                def _vopen(path, mode="r", *a, **kw):
                    return _VFile(path, mode)

                g = {"__builtins__": __builtins__, "open": _vopen}
                try:
                    exec(m["code"], g)  # noqa: S102 - replay of recorded worker op
                    stats["bash_mut"] += 1
                except Exception as ex:  # noqa: BLE001
                    stats.setdefault("bash_python_failed", []).append((str(ex)[:100],))
            elif op_kind == "node":
                # recorded `node -e` mutation (PL-033 doctrine): executed
                # with a REAL node subprocess whose fs is shimmed onto the
                # in-memory tree. The dumped virtual tree replaces `files`
                # wholesale (deletes included) — partial-application
                # semantics match the worker's sequential execution.
                st, newfiles, note = _run_node_eval(m["code"], m.get("cwd", ""), files)
                if st == "ok":
                    files.clear()
                    files.update(newfiles)
                    stats["bash_mut"] += 1
                    stats["node_eval"] = stats.get("node_eval", 0) + 1
                elif st == "skip":
                    stats.setdefault("node_eval_skipped", []).append(note)
                else:
                    stats.setdefault("bash_node_failed", []).append(note)
        elif kind == "surgery":
            _, _, _, _, (order, s) = item
            if s.get("op") == "split":
                rel = s["target"]
                content = files.get(rel)
                if content is None or s["marker"] not in content:
                    stats.setdefault("surgery_failed", []).append(order)
                else:
                    idx = content.index(s["marker"])
                    files[rel] = content[:idx].rstrip() + "\n"
                    files[s["new_file"]] = s["header"] + content[idx:]
                    stats["surgery_ok"] = stats.get("surgery_ok", 0) + 1
            elif s.get("op") == "append":
                rel = s["target"]
                files[rel] = files.get(rel, "") + s["content"]
                stats["surgery_ok"] = stats.get("surgery_ok", 0) + 1
            elif s.get("op") == "python":
                # execute the worker's python mutation against the virtual
                # in-memory tree (open() is shimmed onto the files dict)
                cwd = s.get("cwd", "")
                import types as _types

                class _VFile:
                    def __init__(self, path, mode="r"):
                        self._rel = (cwd + "/" + path) if cwd else path
                        self._mode = mode
                        if any(m in mode for m in ("w", "a")):
                            # 'w' truncates immediately; 'a' keeps content
                            if "w" in mode and "a" not in mode:
                                files[self._rel] = ""
                        self._closed = False
                    def read(self):
                        return files.get(self._rel, "")
                    def write(self, data):
                        # write-through: bare open(p,'w').write(s) must persist
                        files[self._rel] = files.get(self._rel, "") + data
                        return len(data)
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        return False

                def _vopen(path, mode="r", *a, **kw):
                    return _VFile(path, mode)

                g = {"__builtins__": __builtins__, "open": _vopen}
                try:
                    exec(s["code"], g)  # noqa: S102 - replay of recorded op
                    stats["surgery_ok"] = stats.get("surgery_ok", 0) + 1
                except Exception as ex:  # noqa: BLE001
                    stats.setdefault("surgery_failed", []).append((order, str(ex)[:120]))

    if only:
        files = {p: c for p, c in files.items() if p.startswith(only)}

    if bash_skipped:
        stats["bash_unparsed_redirects"] = sum(bash_skipped.values())
        stats["bash_skipped_ops"] = sorted(bash_skipped.keys())
    print(json.dumps(stats))
    print(f"final file set: {len(files)}")
    for p in sorted(files):
        print(f"  {p} ({len(files[p])} chars)")

    if dry:
        return 0
    for rel, content in files.items():
        dest = os.path.join(station, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as f:
            f.write(content)
    print(f"applied {len(files)} files to {station}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
