#!/usr/bin/env python3
"""server_watch.py — tab-independent worker watcher (server-side truth only).

Polls the chats API (batch_probe lineage) for the R0 worker sessions; NO DOM,
NO tabs, NO re-dispatch. Pure observation + outbox notices. Exits when all
sessions reach a terminal state (done:true assistant turn with a filled
report, or chat death), or after the window expires.

Usage: server_watch.py <window-hours, default 8>
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
from batch_probe import call  # noqa: E402

SESSIONS = {
    "post006": "f42b1ba5-c97b-415b-8d45-5944e83988db",
    "gbim003": "cb997d53-dbb7-458f-a9b7-f8c378745405",
}
OUTBOX = "/home/z/replay2/scripts/flags/agent_outbox.jsonl"
LOG = "/home/z/replay2/scripts/logs/server_watch.log"
POLL = 120  # 2 min — fast spawn-phase feedback (notices fire only on transitions)

HEX40 = __import__("re").compile(r"\b[0-9a-f]{40}\b")
PLACEHOLDER = __import__("re").compile(r"<[A-Za-z0-9_ -]{4,40}>")


def log(*a):
    line = " ".join(str(x) for x in a)
    print(time.strftime("[%H:%M:%S]"), line, flush=True)
    with open(LOG, "a") as f:
        f.write(time.strftime("[%H:%M:%S] ") + line + "\n")


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def state_of(cid):
    """Return (phase, assistant_chars, done, filled) for a chat."""
    try:
        chat = call(f"/api/v1/chats/{cid}")
        c = chat.get("chat") or chat
        msgs = (c.get("history") or {}).get("messages") or {}
        if isinstance(msgs, list):
            msgs = {m.get("id", str(i)): m for i, m in enumerate(msgs)}
        if not msgs:
            return ("empty", 0, False, False)
        ids = [m.get("id") for m in msgs.values() if m.get("id")]
        batch = call(f"/api/v1/chats/{cid}/messages/batch", {"ids": ids}, timeout=60)
        data = (batch.get("data") or batch.get("messages")) or {}
        best = None
        for m in data.values():
            if not m:
                continue
            if (m.get("role") or "assistant") == "assistant":
                if best is None or len(json.dumps(m)) > len(json.dumps(best)):
                    best = m
        if best is None:
            return ("queued", 0, False, False)
        whole = json.dumps(best)
        chars = len(whole)
        done = best.get("done") is True
        filled = False
        start = 0
        while True:
            mi = whole.find("COMPLETION REPORT", start)
            if mi < 0:
                break
            win = whole[mi:mi + 900]
            if HEX40.search(win) and not PLACEHOLDER.search(win):
                filled = True
            start = mi + 1
        return ("generating" if not done else "done", chars, done, filled)
    except Exception as e:
        return (f"err:{type(e).__name__}", 0, False, False)


def main():
    window_h = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    deadline = time.time() + window_h * 3600
    prev = {}
    log(f"server_watch armed: {list(SESSIONS)} window={window_h}h poll={POLL}s")
    while time.time() < deadline:
        alive = 0
        for name, cid in SESSIONS.items():
            phase, chars, done, filled = state_of(cid)
            key = (phase, chars, done, filled)
            if prev.get(name) != key:
                log(f"{name}: phase={phase} chars={chars} done={done} filled={filled}")
                if phase == "generating" and prev.get(name, ("", 0, 0, 0))[0] != "generating":
                    outbox(f"[server-watch] {name} GENERATION STARTED (chars={chars}) — worker is live.")
                if phase == "done":
                    outbox(f"[server-watch] {name} TURN DONE (chars={chars}, filled_report={filled}) — "
                           f"{'ready for Lead harvest.' if filled else 'report gate NOT passed — Lead review needed.'}")
                if phase.startswith("err"):
                    outbox(f"[server-watch] {name} probe error: {phase}")
                prev[name] = key
            if not (phase == "done" and filled):
                alive += 1
        if alive == 0:
            log("all sessions terminal (done + filled) — exiting")
            outbox("[server-watch] ALL R0 SESSIONS COMPLETE (done + filled reports). Lead: harvest now.")
            return 0
        time.sleep(POLL)
    log("window expired — standing down (Lead re-arms on next wake)")
    outbox("[server-watch] window expired with sessions still un-terminal. Lead: re-arm or diagnose.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
