#!/usr/bin/env python3
"""r31_watch.py — the lean HTTP-truth watcher for the R31 worker (account-chrome).

Doctrine (lesson-64 truth-surface law + the r29-cycle-3 rebuild, cloned from
r30a_watch.py with ONE change): the chat id is DISCOVERED dynamically (title
match "R31") because this watcher is armed by the hold daemon the moment the
dispatch lands — the id is not known at write time.

States per poll -> stdout (log):
  DISCOVER chat=<id> | SURVIVED n_msgs=<k> | GENERATING | COMPLETE | DEAD | LIST-MISS

Flags: flags/r31-complete (marker file w/ the report tail) on COMPLETE.
       flags/r31-dead on DEAD (the lead refires from the staged prompt).
"""
import json
import subprocess
import sys
import time

CHATS = "/home/z/replay2/scripts/chats_http.py"
PY = "/home/z/.venv/bin/python3"
MARKER = "=== R31 COMPLETION REPORT ==="
FLAGS = "/home/z/replay2/scripts/flags"
POLL_FAST = 30      # s, first 20 polls (the instability window)
POLL_SLOW = 120     # s, after
HORIZON_S = 14 * 3600
TITLE_KEY = "R31"


def run(*args):
    p = subprocess.run([PY, CHATS, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def discover_chat():
    """Find the R31 chat id from the list ('abc12345-67  Title')."""
    rc, out = run("list", "400")
    if rc != 0:
        return None
    for line in out.splitlines():
        if TITLE_KEY in line and line.strip()[0:1].isalnum():
            parts = line.split()
            if parts and len(parts[0]) >= 8:
                return parts[0]
    return None


def assistant_marker(out):
    lines = out.strip().splitlines()
    roles = [l.strip() for l in lines if l.strip().startswith("[")]
    if not roles:
        return False
    last = roles[-1]
    return last.startswith("[assistant]") and "len=0" not in last


def main():
    t0 = time.time()
    chat_id = None
    # deterministic path first: the hold daemon pins the id from the registry
    try:
        pinned = open(f"{FLAGS}/r31-chat-id").read().strip()
        if len(pinned) >= 8:
            chat_id = pinned
            print(f"PINNED chat={chat_id}", flush=True)
    except FileNotFoundError:
        pass
    misses = 0
    polls = 0
    maxlen = 0
    while time.time() - t0 < HORIZON_S:
        polls += 1
        try:
            if chat_id is None:
                chat_id = discover_chat()
                if chat_id is None:
                    print(f"[{time.strftime('%H:%M:%S')}] no R31 chat yet "
                          f"(dispatch hold cycle running?)", flush=True)
                    time.sleep(POLL_FAST)
                    continue
                print(f"DISCOVER chat={chat_id}", flush=True)
                open(f"{FLAGS}/r31-chat-id", "w").write(chat_id + "\n")
            # list check (8-char prefix; the list truncates ids)
            rc, lout = run("list", "400")
            in_list = chat_id[:8] in lout
            rc, out = run("detail", chat_id)
            if not in_list:
                misses += 1
                print(f"[{time.strftime('%H:%M:%S')}] LIST-MISS ({misses}/2)",
                      flush=True)
                if misses >= 2 and rc != 0:
                    print("DEAD: absent from list + detail failing — the "
                          "death signature. Refire flag written.", flush=True)
                    open(f"{FLAGS}/r31-dead", "w").write(
                        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
                    return 1
                time.sleep(15)
                continue
            misses = 0
            if MARKER in out and assistant_marker(out):
                print("COMPLETE: marker + assistant report present.",
                      flush=True)
                open(f"{FLAGS}/r31-complete", "w").write(out[-4000:] + "\n")
                return 0
            lens = [int(l.split("len=")[1]) for l in out.splitlines()
                    if "len=" in l and "]" in l]
            cur = max(lens) if lens else 0
            if rc == 0:
                if cur > maxlen:
                    maxlen = cur
                    print(f"[{time.strftime('%H:%M:%S')}] GENERATING "
                          f"maxlen={maxlen} msgs={len(lens)}", flush=True)
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] SURVIVED "
                          f"msgs={len(lens)} maxlen={maxlen}", flush=True)
        except Exception as e:  # transport errors never count as destruction
            print(f"[{time.strftime('%H:%M:%S')}] transport flap: {e}",
                  flush=True)
        time.sleep(POLL_FAST if polls <= 20 else POLL_SLOW)
    print("HORIZON reached without completion — lead decision required.",
          flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
