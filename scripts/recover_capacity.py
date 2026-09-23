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


# --- zombie gate (86g doctrine, re-applied 2026-09-23 after wipe #3) ---------
# The platform WIPES assistant content after turn death/completion, so chat
# EXISTENCE + empty content proves nothing. The only structural tell for a
# never-spawned chat: the created->updated span never grew (real workers
# update for 33min+; capacity-bounced/staged landings freeze at 4-6s).
ZOMBIE_MAX_SPAN_S = 600   # a span that never passed 10min = no turn ever ran
ZOMBIE_MIN_AGE_S = 180    # do not judge chats younger than 3 minutes
TURN_SPAWN_WAIT_S = 360   # rc=0 spawn-verification window (observed spawns: <=6min)


def _chat_turn_spawned(chat_uuid):
    """True once the turn exists (ANY assistant message, even an empty
    placeholder — the platform creates it at turn start); False while only
    the user prompt is there; None on tooling failure."""
    try:
        sys.path.insert(0, BASE)
        import chats_http
        data = chats_http.api(f"/api/v1/chats/{chat_uuid}")
        rec = data.get("data", data) if isinstance(data, dict) else {}
        inner = rec.get("chat", {}) or rec
        msgs = (inner.get("history", {}) or {}).get("messages", {})
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        return any(m.get("role") == "assistant" for m in msgs)
    except Exception:
        return None


def _chat_zombie_server_side(chat_uuid):
    """True only for a never-spawned (zombie) chat; False for turn-bearing
    or lived chats; None on tooling failure (caller must preserve the flag)."""
    try:
        sys.path.insert(0, BASE)
        import chats_http
        data = chats_http.api(f"/api/v1/chats/{chat_uuid}")
        rec = data.get("data", data) if isinstance(data, dict) else {}
        inner = rec.get("chat", {}) or rec
        msgs = (inner.get("history", {}) or {}).get("messages", {})
        if isinstance(msgs, dict):
            msgs = list(msgs.values())
        # turn-bearing: any assistant message with committed content
        for m in msgs:
            if m.get("role") == "assistant" and isinstance(m.get("content"), str) \
                    and len(m["content"]) > 0:
                return False
        # timestamps: snake_case on the OUTER record (observed 2026-09-23:
        # created_at/updated_at epoch seconds), camelCase tried as fallback
        ca = rec.get("created_at") or inner.get("createdAt") or inner.get("created_at")
        ua = rec.get("updated_at") or inner.get("updatedAt") or inner.get("updated_at")
        if isinstance(ca, (int, float)) and isinstance(ua, (int, float)):
            span, age = ua - ca, time.time() - ca
            if span > ZOMBIE_MAX_SPAN_S:
                return False        # lived long enough = worker range
            if age < ZOMBIE_MIN_AGE_S:
                return False        # too young to judge
            return True             # no turn, span frozen, old enough = zombie
        # no timestamps available: fall back to message-shape (86g truth table:
        # no assistant at all, or only empty placeholders)
        if time.time() - _chat_age_fallback(chat_uuid) < ZOMBIE_MIN_AGE_S:
            return False
        return not any(m.get("role") == "assistant" for m in msgs) or \
            all(not (isinstance(m.get("content"), str) and m["content"])
                for m in msgs if m.get("role") == "assistant")
    except Exception:
        return None


def _chat_age_fallback(chat_uuid):
    """Best-effort chat age when createdAt is absent (registry ts fallback)."""
    try:
        for line in reversed([l for l in open(REG).read().split("\n") if l.strip()]):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if chat_uuid in (r.get("url") or ""):
                return float(r.get("ts") or 0)
    except Exception:
        pass
    return 0.0


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
        # 2026-09-16 (TL): an empty cache made every check return None and the
        # callers' legacy trust-registry path DISARMED the assault on phantoms
        # (observed: dep-001 poller cleared its flag on phantom 4328a88f with
        # a 0-byte chat_token). Self-heal: extract a fresh token from a live
        # chat.z.ai tab (chats_http.get_token writes the cache as a side effect).
        try:
            sys.path.insert(0, BASE)
            import chats_http
            tok = chats_http.get_token().strip().strip('"')
        except Exception:
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
            if server_live is None:
                # 2026-09-16 (TL): tooling failure must NEVER disarm the
                # assault (legacy trust-registry behavior cleared the flag on
                # a phantom when the token cache was empty). Exit with the
                # flag intact — the supervisor re-arms a fresh poller which
                # re-reads/refreshes the token.
                print("server check TOOLING FAILURE (None) — flag preserved, NOT disarming; supervisor will re-arm", flush=True)
                return 5
            # 2026-09-23 (TL): the upstream "cosmetic popup" create can exit
            # rc=0 on a CAPACITY BOUNCE (prompt landed, turn never spawned —
            # observed twice on pa-004). Verify the turn actually SPAWNS
            # before disarming: poll for the assistant placeholder up to
            # TURN_SPAWN_WAIT_S. Spawn -> real success (clear). Timeout ->
            # void + keep fighting. Tooling failure -> legacy clear (the
            # zombie gate + pa_server_watch re-arm remain the backstops).
            m_url = re.search(r"/c/([0-9a-f-]{36})", _last_sent_url(name) or "")
            if m_url:
                chat_uuid = m_url.group(1)
                deadline = time.time() + TURN_SPAWN_WAIT_S
                spawned = None
                print(f"rc=0 — verifying turn spawn on {chat_uuid[:8]} "
                      f"(up to {TURN_SPAWN_WAIT_S}s)...", flush=True)
                while time.time() < deadline:
                    spawned = _chat_turn_spawned(chat_uuid)
                    if spawned is True:
                        break
                    if spawned is None:
                        print("spawn check TOOLING FAILURE — falling back to legacy clear", flush=True)
                        break
                    time.sleep(30)
                if spawned is False:
                    print("rc=0 but the turn NEVER SPAWNED within the window — "
                          "voiding + continuing assault", flush=True)
                    _void_phantom(name, _last_sent_url(name))
                    time.sleep(20)
                    continue
                if spawned is True:
                    print("turn SPAWNED — assault complete, disarming", flush=True)
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
                if server_live is None:
                    # 2026-09-16 (TL): same tooling-failure guard as the rc=0 path.
                    print("server check TOOLING FAILURE (None) — flag preserved, NOT disarming; supervisor will re-arm", flush=True)
                    return 5
                # 86g zombie gate (re-applied 2026-09-23 after wipe #3): the
                # chat EXISTS but may have never spawned a turn (capacity
                # bounce / staged landing). Content-wipe discipline: existence
                # + empty content proves NOTHING — the created->updated span
                # is the only structural tell. Zombie -> void + keep fighting.
                m_url = re.search(r"/c/([0-9a-f-]{36})", _last_sent_url(name) or "")
                zombie = _chat_zombie_server_side(m_url.group(1)) if m_url else None
                if zombie is None:
                    print("zombie check TOOLING FAILURE (None) — flag preserved, NOT disarming; supervisor will re-arm", flush=True)
                    return 5
                if zombie:
                    print("chat exists but NEVER SPAWNED a turn (zombie: no content, span frozen) — voiding + continuing assault", flush=True)
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
