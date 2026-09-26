#!/usr/bin/env python3
"""r32_watch.py — the HTTP-truth watcher for the R32 worker (shorts rail).

Cloned from r31_watch.py with the chat id PINNED (the lesson: title-based
DISCOVER truncates; the full id is the truth). Polls the messages API:
  DISCOVER/PINNED -> SURVIVED n_msgs | GENERATING | COMPLETE | DEAD

Flags: flags/r32-complete (the report tail) on COMPLETE.
       flags/r32-dead on DEAD (the lead refires from the staged prompt).
"""
import json
import subprocess
import sys
import time

CHATS = "/home/z/replay2/scripts/chats_http.py"
PY = "/home/z/.venv/bin/python3"
CHAT_ID = "ca87c5cf-ea75-44ed-a972-70c4bef25f21"
MARKER = "=== R32 COMPLETION REPORT ==="
FLAGS = "/home/z/replay2/scripts/flags"
POLL_FAST = 30
POLL_SLOW = 120
HORIZON_S = 14 * 3600


def run(*args):
    p = subprocess.run([PY, CHATS, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def chat_detail():
    rc, out = run("detail", CHAT_ID)
    if rc != 0 or "title:" not in out:
        return None
    msgs = 0
    last_len = 0
    marker = False
    for line in out.splitlines():
        if line.strip().startswith("["):
            msgs += 1
            if "len=" in line:
                try:
                    last_len = int(line.split("len=")[1].split()[0])
                except Exception:
                    pass
    return {"msgs": msgs, "last_len": last_len, "raw": out}


def marker_in_chat():
    """Marker check via the full detail raw text (committed content only)."""
    rc, out = run("detail", CHAT_ID)
    return rc == 0 and MARKER in out


def main():
    t0 = time.time()
    slow_after = time.time() + 20 * 60
    log = lambda m: print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}",
                          flush=True)
    log(f"watch start (R32, chat {CHAT_ID[:8]})")
    misses = 0
    while time.time() - t0 < HORIZON_S:
        d = chat_detail()
        if d is None:
            misses += 1
            log(f"DEAD? detail failing (miss {misses})")
            if misses >= 4:
                open(f"{FLAGS}/r32-dead", "w").write(
                    f"dead at {time.strftime('%H:%M:%SZ', time.gmtime())}\n")
                log("DEAD — 4 consecutive detail failures; flag written")
                return 30
            time.sleep(60)
            continue
        misses = 0
        if marker_in_chat():
            open(f"{FLAGS}/r32-complete", "w").write(
                f"complete at {time.strftime('%H:%M:%SZ', time.gmtime())}\n")
            log("COMPLETE — marker in committed content")
            return 0
        log(f"SURVIVED msgs={d['msgs']} lastlen={d['last_len']}")
        time.sleep(POLL_FAST if time.time() < slow_after else POLL_SLOW)
    log("HORIZON reached")
    return 1


if __name__ == "__main__":
    sys.exit(main())
