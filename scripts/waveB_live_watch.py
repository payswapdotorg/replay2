#!/usr/bin/env python3
"""waveB_live_watch.py — passive live-event observer for the Wave B grind.

Tails logs/wave_keepalive.log; when wave_dispatch_sentinel logs a
GENERATING or ADOPTED event for a wave name, this observer (NO dispatch
power, NO assault behavior — purely passive):

  1. finds the browser tab sitting on that chat and repoints
     flags/active_tab.txt so the operator console streams the live session;
  2. posts a short notification to the operator outbox;
  3. writes flags/<name>-live.marker for the Lead's next pass.

Exits when every watched name has gone live, or after MAX_S seconds
(default 14h). Logs to logs/waveB_live_watch.log.

Usage: waveB_live_watch.py name1 name2 name3
"""
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

LOG = os.path.join(BASE, "logs", "wave_keepalive.log")
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
ACTIVE = os.path.join(FLAGS, "active_tab.txt")
MAX_S = 14 * 3600

EV = re.compile(r"\[([\d:]+)\] \[(\w+)\] (GENERATING in ([0-9a-f]{8})|ADOPTED earlier chat ([0-9a-f]{8}))")


def log(line):
    print(time.strftime("[%H:%M:%S]") + f" [live-watch] {line}", flush=True)


def post_outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception as e:
        log(f"outbox write failed: {e}")


def tab_on_chat(cid8):
    try:
        for t in channel.list_tabs():
            if cid8 in (t.get("url") or ""):
                return t.get("id")
    except Exception as e:
        log(f"tab list failed: {e}")
    return None


def main():
    names = sys.argv[1:]
    if not names:
        print(__doc__)
        return 2
    live = set()
    for n in names:
        mk = os.path.join(FLAGS, f"{n}-live.marker")
        if os.path.exists(mk):
            live.add(n)
    log(f"watching {names}; already live: {sorted(live) or 'none'}")
    f = open(LOG, "r")
    f.seek(0, 2)  # tail
    t0 = time.time()
    while len(live) < len(names) and time.time() - t0 < MAX_S:
        line = f.readline()
        if not line:
            time.sleep(4)
            # log rotation/restart safety: if the file shrank, reopen
            try:
                if os.path.getsize(LOG) < f.tell():
                    f.close()
                    f = open(LOG, "r")
            except Exception:
                pass
            continue
        m = EV.search(line)
        if not m:
            continue
        _, name, _, g_cid, a_cid = m.groups()
        if name not in names or name in live:
            continue
        cid8 = g_cid or a_cid
        kind = "now generating" if g_cid else "adopted (earlier chat fired)"
        live.add(name)
        tab = tab_on_chat(cid8)
        if tab:
            open(ACTIVE, "w").write(tab)
            log(f"{name} LIVE ({kind}) chat {cid8}; active_tab -> {tab[:12]}")
            stream_note = "Your console stream now shows the live session."
        else:
            log(f"{name} LIVE ({kind}) chat {cid8}; NO TAB on it yet (Lead will repoint)")
            stream_note = "The Lead will repoint your console stream on the next pass."
        open(os.path.join(FLAGS, f"{name}-live.marker"), "w").write(
            f"{name} live chat={cid8} at {time.strftime('%H:%M:%S')} ({kind})\n")
        post_outbox(f"{name.upper()} IS LIVE — chat {cid8} ({kind}). {stream_note} "
                    f"Wave B remaining: {sorted(set(names) - live) or 'none — full wave airborne'}.")
    log(f"done; live={sorted(live)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
