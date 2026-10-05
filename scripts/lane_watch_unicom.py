#!/usr/bin/env python3
"""lane_watch_unicom.py — UNiCOM-era lane watch daemon (the lead-watch).

The console's live Workers strip surfaces a session ONLY when a FRESH
flags/lane_status.<name>.json exists (the MOS-era lead-watch contract,
src/app/api/workers/route.ts). UNiCOM waves are dispatched server-side,
so this daemon IS the lead-watch. Every ROUND_S seconds it

  1. re-reads flags/session_registry.jsonl — live lanes auto-derive:
     names matching ^unicom- whose latest record is sent=True and whose
     last void (if any) predates that record; a
     flags/<name>-complete.marker retires a lane to state complete;
  2. probes each chat server-side via chats_http.api() (CDP-free,
     lesson-107: Bearer = the cached/durable site JWT, refreshed from a
     live chat.z.ai tab when stale);
  3. writes flags/lane_status.<name>.json
     {state, chars, url, n, n_asst, generating, batches, updated_at, ts}

State mapping (what the console displays):
  generating  — any message has generating=true (agent is streaming)
  working     — chars/message-count moved since the previous round
  queued      — no movement this round (turn closed, pod possibly gone;
                the lastStateLine carries updated-at age for judgment)
  complete    — TL wrote flags/<name>-complete.marker after merge
  probe-error — API call failed twice (fresh mtime keeps the row
                visible with a diagnostic; retried next round)

Agent-session reality (2026-10-05 lesson): workers deliver via GIT with
near-empty chat prose — message-count growth + updated_at are the live
signals, chars flapping is not required for "healthy".
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chats_http

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
HEARTBEAT = os.path.join(FLAGS, "lane_watch_hb")
ROUND_S = 120
NAME_RE = re.compile(r"^unicom-", re.I)
URL_RE = re.compile(r"/c/([0-9a-f-]{36})")

log = lambda m: print(f"[lane_watch {time.strftime('%H:%M:%S')}] {m}", flush=True)


def live_lanes():
    """Registry walk → {name: url} for lanes that are live RIGHT NOW.

    A lane is live when its newest sent=True record postdates its newest
    void; a complete marker only caps the STATE, it does not unwatch the
    lane (the console shows it green instead).
    """
    lanes, order = {}, []
    try:
        with open(REGISTRY) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                name = (r.get("name") or "").lower()
                if not NAME_RE.match(name):
                    continue
                if r.get("action") == "void":
                    lanes.pop(name, None)
                    continue
                if r.get("sent") and r.get("url"):
                    m = URL_RE.search(r["url"])
                    if m and name not in lanes:
                        order.append(name)
                    if m:
                        lanes[name] = r["url"]
    except FileNotFoundError:
        pass
    return {n: lanes[n] for n in order if n in lanes}


def probe(chat_id):
    """One server-side chat probe → status dict (raises on API failure)."""
    data = chats_http.api(f"/api/v1/chats/{chat_id}")
    rec = data.get("data", data) if isinstance(data, dict) else {}
    inner = rec.get("chat", {}) or rec
    msgs = (inner.get("history", {}) or {}).get("messages", {})
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    n_asst = sum(1 for m in msgs if m.get("role") == "assistant")
    chars = 0
    for m in msgs:
        c = m.get("content")
        if isinstance(c, str):
            chars += len(c)
    generating = any(bool(m.get("generating")) for m in msgs)
    return {
        "n": len(msgs),
        "n_asst": n_asst,
        "chars": chars,
        "generating": generating,
        "updated_at": rec.get("updated_at") or inner.get("updated_at") or "",
        "title": rec.get("title") or "",
    }


def write_status(name, url, st):
    st = dict(st)
    st["url"] = url
    st["ts"] = int(time.time())
    with open(os.path.join(FLAGS, f"lane_status.{name}.json"), "w") as fh:
        json.dump(st, fh)


def main():
    os.makedirs(FLAGS, exist_ok=True)
    log(f"armed — {ROUND_S}s rounds, registry-driven, status → lane_status.*")
    prev = {}  # name → (chars, n) last round
    while True:
        lanes = live_lanes()
        open(HEARTBEAT, "w").write(str(int(time.time())))
        for name, url in lanes.items():
            cid = URL_RE.search(url).group(1)
            done = os.path.exists(os.path.join(FLAGS, f"{name}-complete.marker"))
            try:
                st = probe(cid)
            except Exception as first_err:
                # token may be stale — drop the cache, re-eval from a live
                # tab, retry once before declaring probe-error
                try:
                    os.unlink(chats_http.TOKEN_CACHE)
                except OSError:
                    pass
                try:
                    st = probe(cid)
                except Exception as second_err:
                    write_status(name, url, {
                        "state": "probe-error",
                        "error": repr(second_err)[:160],
                    })
                    log(f"{name}: probe-error ({second_err!r} then {first_err!r})")
                    prev.pop(name, None)
                    continue
            if done:
                state = "complete"
            elif st["generating"]:
                state = "generating"
            else:
                moved = prev.get(name) not in (None, (st["chars"], st["n"]))
                state = "working" if moved else "queued"
            prev[name] = (st["chars"], st["n"])
            st["state"] = state
            write_status(name, url, st)
        time.sleep(ROUND_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
