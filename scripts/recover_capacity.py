#!/usr/bin/env python3
"""recover_capacity.py — PERSISTENT AGGRESSIVE capacity assault (operator policy).

Operator (2026-09-09): "do not wait just because a popup tells you to, never
wait, find a way around it ... normally cancelling and retrying works just as
long as you always pick the right model (GLM 5.3), the agents tab and the
full stack skill before resending the prompt."

So this poller NEVER waits out a GLM-5.3 capacity peak: it re-runs the full
verified dispatch (dispatch_worker.create — agents tab + GLM-5.3 + Full-Stack
+ insert + send, cancelling every capacity popup it meets and re-picking the
selections) round after round until the task actually lands and generates.
The supervisor keeps one poller alive PER flag file while it exists; success
(or an already-live session) clears the flag.

Usage: recover_capacity.py [flag-path] [legacy-uuid]
  flag-path  — flags/capacity_recover[.<name>].json (per-session; the
               supervisor passes it explicitly). Defaults to the legacy
               single-slot path for manual invocation.

Flag format: {"name": ..., "prompt_file": ..., "uuid": ..., "tab_id": ...}
Legacy flags {"uuid": ...} are resolved through the session registry.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
# argv[1] = flag path (supervisor passes the per-session flag); argv[1] may
# also be a bare legacy uuid (old supervisor invocation) — detect by suffix.
_arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
if _arg1.endswith(".json"):
    FLAG = os.path.abspath(_arg1)
    _legacy_uuid = sys.argv[2] if len(sys.argv) > 2 else ""
elif _arg1:
    FLAG = os.path.join(BASE, "flags/capacity_recover.json")
    _legacy_uuid = _arg1
else:
    FLAG = os.path.join(BASE, "flags/capacity_recover.json")
    _legacy_uuid = ""
_stem = os.path.basename(FLAG)[len("capacity_recover"):-len(".json")] or ""
PIDFILE = os.path.join(BASE, f"flags/capacity_recover.pid{_stem}")
REG = os.path.join(BASE, "flags/session_registry.jsonl")


def _clear_flag():
    for p in (FLAG, PIDFILE):
        try:
            os.remove(p)
        except Exception:
            pass


def _spec():
    """Resolve (name, prompt_file) from the flag — legacy-registry aware."""
    d = json.load(open(FLAG))
    if d.get("name") and d.get("prompt_file"):
        return d
    uuid = d.get("uuid", "")
    try:
        lines = open(REG).read().split("\n")
    except Exception:
        lines = []
    for line in reversed([l for l in lines if l.strip()]):
        try:
            s = json.loads(line)
        except Exception:
            continue
        if s.get("stage") == "capacity" and (
                uuid in (s.get("url") or "") or (s.get("tab_id") or "").startswith(uuid)):
            d["name"] = s.get("name")
            d["prompt_file"] = s.get("prompt_file")
            return d
    return None


def _chat_live_server_side(name):
    """Lesson-98/106: the ONLY landing truth is the server chats list.

    Walks the registry in order (a later void/failed/done row invalidates
    earlier create rows) to find the current live row's /c/ URL, then checks
    the chats list over plain HTTP (lesson-107 token pattern). Returns
    True (chat exists), False (phantom — absent from list / detail dead),
    or None (tooling failure — caller should PRESERVE legacy registry-trust
    behavior so a broken token never dead-locks or infinite-loops).
    """
    url = None
    live = False
    try:
        for line in open(REG).read().split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("name") != name:
                continue
            if r.get("action") in ("void", "voided", "failed", "done"):
                live = False
                url = None
            elif r.get("sent") and r.get("url"):
                live = True
                url = r.get("url")
    except Exception:
        return None
    if not live or not url:
        return False
    m = re.search(r"/c/([0-9a-f-]{36})", url)
    if not m:
        return None
    tok = ""
    cache = os.path.join(BASE, "flags", "chat_token")
    if os.path.isfile(cache):
        try:
            tok = open(cache).read().strip().strip('"')
        except Exception:
            tok = ""
    if not tok:
        return None
    try:
        req = urllib.request.Request(
            "https://chat.z.ai/api/v1/chats/list?limit=100",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return None
    items = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(items, dict):
        items = items.get("items", [])
    return any((it.get("id") or "") == m.group(1) for it in items)


def _last_sent_url(name):
    """The most recent sent=true row's URL for `name` (for void notes)."""
    url = None
    try:
        for line in open(REG).read().split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("name") == name and r.get("sent") and r.get("url"):
                url = r.get("url")
    except Exception:
        pass
    return url or "unknown-url"


def _void_phantom(name, url):
    """Invalidate a phantom sent-row so later scans do not steal it."""
    try:
        with open(REG, "a") as f:
            f.write(json.dumps({"action": "void", "name": name,
                                "note": f"phantom send: chat {url} absent from chats list — capacity-swallowed (poller auto-void, lesson 98/106)"}) + "\n")
    except Exception:
        pass


def main():
    spec = _spec()
    if not spec or not spec.get("name") or not spec.get("prompt_file"):
        print("flag unresolvable (no name/prompt_file) — clearing", flush=True)
        _clear_flag()
        return 4
    name, prompt_file = spec["name"], spec["prompt_file"]
    # resolve relative prompt paths against the repo root (replay2/) — flags
    # written before the absolute-path fix (or by hand) may carry relative
    # paths; a bare FileNotFoundError must not read as "already live"
    if not os.path.isabs(prompt_file):
        prompt_file = os.path.join(os.path.dirname(BASE), prompt_file)
    if not os.path.exists(prompt_file):
        print(f"prompt file missing: {prompt_file} — clearing flag", flush=True)
        _clear_flag()
        return 4
    print(f"aggressive recovery: {name} <- {prompt_file} (never waits out capacity)", flush=True)
    for attempt in range(240):  # up to ~8h of active assault; supervisor re-arms
        rc = subprocess.call([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                              "create", name, prompt_file])
        print(f"[{attempt}] create rc={rc}", flush=True)
        if rc == 0:
            # Lesson-98/106 hardening: a create can exit 0 on a PHANTOM send
            # (chat destroyed server-side). Verify against the chats list
            # before clearing the flag; on phantom, void the row and keep
            # fighting (observed: wfx-030d poller self-cleared on its own
            # phantom and silently disarmed the item).
            server_live = _chat_live_server_side(name)
            if server_live is False:
                print("rc=0 but chat ABSENT from server list — phantom; voiding + continuing assault", flush=True)
                _void_phantom(name, _last_sent_url(name))
                time.sleep(20)
                continue
            _clear_flag()
            return 0
        if rc == 1:
            # 2026-09-10 fix: a CRASHED create also exits 1 (unhandled
            # exception) — verify the session is genuinely live in the
            # registry before aborting the assault (false positive ended
            # recovery with no session created).
            # 2026-09-13 fix (TL): the scan ORDERING — a sent=True create row
            # from BEFORE a later void/failed/done row falsely matched 'live'
            # (observed: w203's 06:24 culled-dispatch row made the poller
            # clear a fresh flag as 'recovered elsewhere'). Registry
            # semantics (see _find in dispatch_worker): a later
            # void/failed/done invalidates every EARLIER create for the
            # name. Walk rows in order; an invalidation resets live.
            live = False
            try:
                for line in open(REG).read().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if r.get("name") != name:
                        continue
                    if r.get("action") in ("void", "failed", "done"):
                        live = False  # invalidates every earlier create row
                    elif r.get("sent") and r.get("action") is None:
                        live = True
            except Exception:
                pass
            if live:
                server_live = _chat_live_server_side(name)
                if server_live is False:
                    print("registry says live but chat ABSENT from server list — phantom; voiding + retrying", flush=True)
                    _void_phantom(name, _last_sent_url(name))
                    time.sleep(20)
                    continue
                print("session already live — recovered elsewhere", flush=True)
                _clear_flag()
                return 0
            print("rc=1 but session NOT in registry (crashed create) — retrying", flush=True)
            # 2026-09-10 fix: an unsent/stale create record blocks every retry
            # (create() exits 1 on _find hit). Invalidate it so the next
            # attempt starts fresh (registry semantics: failed action
            # invalidates earlier creates for the name).
            try:
                with open(REG, "a") as f:
                    f.write(json.dumps({"action": "failed", "name": name,
                                        "note": "stale unsent record invalidated by recovery retry"}) + "\n")
                print("stale record invalidated — next create starts fresh", flush=True)
            except Exception:
                pass
            time.sleep(20)
            continue
        # rc==3: create ran its full in-process assault and re-staged the
        # flag; go again immediately (short gap). rc==2/other: give the page
        # a moment, then the next create closes stale tabs and retries.
        time.sleep(20 if rc == 3 else 45)
    return 3


if __name__ == "__main__":
    try:
        with open(PIDFILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    sys.exit(main())
