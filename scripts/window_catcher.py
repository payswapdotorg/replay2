#!/usr/bin/env python3
"""window_catcher.py — the GLM-5.3 admission-window fast net.

REBUILT 2026-10-16 (recycle #24/#25 wiped the runtime-only original; this
faithfully restores the window-war-1 spec, field-proven 2026-10-15):

  - the chat-list `message_count` is a DEAD signal (reads 0 even for
    admitted chats) — the LLM-GENERATED TITLE is the admission law: a chat
    that gains a non-"New Chat" title was ADMITTED and generated, which
    means a capacity window was OPEN within the last cycle;
  - every CYCLE_EVERY seconds: pull the chat list via the token API
    (chats_http.py, CDP-free, token cached in flags/chat_token). On an API
    flap, one immediate retry (the ~30-50% flap rate would otherwise halve
    the blind rounds);
  - WINDOW SIGNAL = any chat that gains a title it did not have in the
    previous cycle (baseline learned on the first cycle — pre-existing
    titles are not signals);
  - if the LANE (lane_list.txt) is unspawned (its latest-live chat is
    untitled, dead or server-gone) when a window signal fires → instant
    `unstick.py <lane>` (dismiss the capacity modal + resend the staged
    prompt on the lane's live session). The unstick is harmless on a dead
    lane (exit 3, needs re-dispatch — the sentinel's recover owns that
    path); it becomes the seconds-level pressure the moment a live lane
    session exists;
  - STAND DOWN while the lane's own chat carries a title (the lane
    spawned; no resend pressure needed);
  - heartbeat: flags/window_catcher_hb = "<epoch> watch chats=N sid=<id8>"
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import chats_http  # noqa: E402  (token-cached /api/v1/chats* client)

FLAGS = os.path.join(BASE, "flags")
HB_PATH = os.path.join(FLAGS, "window_catcher_hb")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
LANE_LIST = os.path.join(FLAGS, "lane_list.txt")
UNSTICK = os.path.join(BASE, "unstick.py")
CYCLE_EVERY = 45
UNTITLED = "New Chat"
LANE_RE = re.compile(r"^[wt]\d+-\d+[a-z]?$")
PY = sys.executable


def log(msg):
    print(f"[window_catcher {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def lane_names():
    try:
        return [l.strip() for l in open(LANE_LIST) if l.strip()]
    except OSError:
        return []


def lane_chats():
    """{lane: chat_id} from the latest live (non-void/failed/done) rows."""
    out = {}
    try:
        rows = [json.loads(l) for l in open(REGISTRY) if l.strip()]
    except (OSError, ValueError):
        return out
    for r in rows:
        name = r.get("name", "")
        if LANE_RE.fullmatch(name) and r.get("action") not in ("void", "failed", "done"):
            m = re.search(r"/c/([0-9a-f-]{36})", r.get("url") or "")
            if m:
                out[name] = m.group(1)
    keep = set(lane_names())
    return {n: c for n, c in out.items() if n in keep}


def fetch_chats():
    """[{id,title}] via the token API; one flap-retry. None on hard failure."""
    for attempt in (1, 2):
        try:
            data = chats_http.api("/api/v1/chats/list?limit=200")
            if isinstance(data, dict):
                data = data.get("data") or data.get("chats") or []
            if not isinstance(data, list):
                raise TypeError(f"unexpected chat-list shape: {type(data).__name__}")
            return [c for c in data if isinstance(c, dict)]
        except Exception as exc:  # noqa: BLE001 — flap tolerance by design
            if attempt == 2:
                log(f"chat list hard-fail: {exc!r}")
                return None
            time.sleep(2)  # immediate flap-retry
    return None


def unstick_lane(lane):
    try:
        r = subprocess.run(
            [PY, UNSTICK, lane],
            capture_output=True, text=True, timeout=120, cwd=BASE,
        )
        tail = (r.stdout or r.stderr or "").strip().splitlines()
        log(f"unstick {lane} rc={r.returncode} :: {' | '.join(tail[-3:])[:300]}")
        return r.returncode
    except subprocess.TimeoutExpired:
        log(f"unstick {lane} TIMEOUT")
        return -1


def heartbeat(n_chats, sid):
    try:
        with open(HB_PATH, "w") as f:
            f.write(f"{int(time.time())} watch chats={n_chats} sid={sid or '-'}\n")
    except OSError:
        pass


def main():
    log(f"net up (cycle={CYCLE_EVERY}s; title law; lanes={lane_names()})")
    seen_titles = None  # baseline learned on first successful cycle
    while True:
        lanes = lane_chats()
        chats = fetch_chats()
        if chats is None:
            heartbeat(0, next(iter(lanes.values()), None))
            time.sleep(CYCLE_EVERY)
            continue

        titled = {}
        for c in chats:
            cid = c.get("id") or ""
            title = (c.get("title") or "").strip()
            if cid and title and title != UNTITLED:
                titled[cid] = title

        if seen_titles is None:
            seen_titles = titled
            log(f"baseline: {len(titled)} titled chats; lanes={ {n: c[:8] for n, c in lanes.items()} }")
        else:
            fresh = {cid: t for cid, t in titled.items()
                     if seen_titles.get(cid) != t}
            # a title CHANGE on an already-titled chat is not an admission
            fresh = {cid: t for cid, t in fresh.items() if cid not in seen_titles}
            if fresh:
                log(f"WINDOW SIGNAL: {len(fresh)} fresh title(s) :: "
                    f"{ {c[:8]: t[:40] for c, t in list(fresh.items())[:3]} }")
                for lane, cid in lanes.items():
                    lane_title = titled.get(cid)
                    if lane_title:
                        log(f"{lane}: own chat titled ('{lane_title[:40]}') — standing down")
                        continue
                    log(f"{lane}: unspawned during a window — firing unstick")
                    unstick_lane(lane)
            seen_titles = titled

        heartbeat(len(chats), next(iter(lanes.values()), None))
        time.sleep(CYCLE_EVERY)


if __name__ == "__main__":
    main()
