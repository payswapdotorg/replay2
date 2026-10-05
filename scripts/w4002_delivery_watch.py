#!/usr/bin/env python3
"""w4002_delivery_watch.py — watch the W4-002 worker through to delivery.

The worker (chat 476b5e05, revived 2026-10-05 09:57Z) executes the
self-contained P4-W4-002 brief: builds on base 852941a, pushes branch
work/P4-W4-002, and reports in-chat (branch + HEAD SHA + receipts) as
its final message. The TL harvests after.

Poll every 5 min:
  - git ls-remote for work/P4-W4-002 (branch truth; base 852941a excluded)
  - chat record: newest assistant content + message count

States:
  - DELIVERED: branch exists with commits beyond base OR newest assistant
    message carries the report (mentions work/P4-W4-002 + a 40-hex SHA,
    content > 2000 chars) -> flags/w4002_delivered (with HEAD SHA), exit 0
  - WORKING: content growing or turn generating -> keep watching
  - STALLED: no content growth for STALL_AFTER (default 90 min) AND turn
    not generating -> flags/w4002_stalled (TL applies the s8 cure), keep
    watching (the stall may clear on its own; the flag is the alert)
  - WINDOW (default 14h) expired -> flags/w4002_watch_timeout, exit 1

Usage: dfork_launch.py logs/w4002_delivery.log python3 w4002_delivery_watch.py
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import chats_http  # noqa: E402

CHAT = "476b5e05-b67c-47f0-8c3f-a5e7cd3c429c"
BRANCH = "work/P4-W4-002"
BASE_SHA = "852941a"
REMOTE = os.environ.get(
    "PAYSWAP_REMOTE",
    "https://github.com/payswapdotorg/payswap.org.git")
FLAGS = os.path.join(BASE, "flags")
CYCLE = 300          # 5 min
STALL_AFTER = 90 * 60
WINDOW = 14 * 3600


def log(msg):
    print(f"[w4002-dlv {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def branch_head():
    """Return the remote HEAD sha of the work branch, or None."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", REMOTE, f"refs/heads/{BRANCH}"],
            capture_output=True, text=True, timeout=60).stdout.strip()
        return out.split()[0] if out else None
    except Exception:
        return None


def chat_state():
    """(n_msgs, newest_assistant_len, newest_assistant_content, generating)."""
    try:
        d = chats_http.api(f"/api/v1/chats/{CHAT}")
        msgs = ((d.get("chat") or {}).get("history") or {}).get("messages") or {}
        best = None
        for m in msgs.values():
            if m.get("role") == "assistant":
                if best is None or (m.get("timestamp") or 0) >= (best.get("timestamp") or 0):
                    best = m
        if not best:
            return len(msgs), 0, "", None
        c = best.get("content") or ""
        return len(msgs), len(c), c, best.get("generating")
    except Exception as e:
        return -1, -1, f"err:{type(e).__name__}", None


def looks_like_report(text):
    return ("work/P4-W4-002" in text and
            bool(re.search(r"\b[0-9a-f]{40}\b", text)))


def main():
    log(f"armed — branch {BRANCH} (base {BASE_SHA}), chat {CHAT[:8]}, "
        f"cycle {CYCLE}s, stall {STALL_AFTER//60}m, window {WINDOW//3600}h")
    t0 = time.time()
    last_len = -1
    last_growth = time.time()
    stall_flagged = False
    while time.time() - t0 < WINDOW:
        time.sleep(CYCLE)
        try:
            sha = branch_head()
            n, alen, ahead, gen = chat_state()
            if n < 0:
                log(f"chat probe failed ({ahead}) — retrying")
                continue
            # server-side content can lag the live DOM; growth resets stall
            if alen > last_len:
                last_len = alen
                last_growth = time.time()
                stall_flagged = False
            delivered = False
            if sha and not sha.startswith(BASE_SHA[:8]):
                log(f"BRANCH LIVE at {sha[:10]}")
                delivered = True
            if alen > 2000 and looks_like_report(ahead):
                log("REPORT-shaped final message present")
                delivered = True
            if delivered:
                head = sha or (re.search(r"\b[0-9a-f]{40}\b", ahead) or [""])[0]
                open(os.path.join(FLAGS, "w4002_delivered"), "w").write(
                    json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "head": head, "assistant_len": alen, "n_msgs": n}))
                log(f"DELIVERED — head {head[:10]}, assistant_len {alen}")
                return 0
            idle = int((time.time() - last_growth) // 60)
            log(f"working — branch {'absent' if not sha else sha[:10]}, "
                f"n={n}, alen={alen}, gen={gen}, idle {idle}m")
            if (idle * 60 >= STALL_AFTER and gen is not True
                    and not stall_flagged and alen >= 0):
                open(os.path.join(FLAGS, "w4002_stalled"), "w").write(
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                log(f"STALLED — no growth {idle}m, turn not generating "
                    f"(flag set; TL s8 cure candidate)")
                stall_flagged = True
        except Exception as e:
            log(f"cycle error: {type(e).__name__}: {e}")
    open(os.path.join(FLAGS, "w4002_watch_timeout"), "w").write(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log("WINDOW EXPIRED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
