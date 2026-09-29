#!/usr/bin/env python3
"""w090c_watch.py — corrected W090C worker watch (the false-positive fix).

login_watch_dispatch v2 exited at 21:46 because the chat body contained
"W090C COMPLETION REPORT" — but that was the ECHOED PROMPT TEMPLATE (the
work order itself contains the literal block with '<your commit sha>'
placeholders). The worker was still generating.

This watcher classifies with the un-forgeable signature instead:
  REAL REPORT: /W090C COMPLETION REPORT[\s\S]{0,300}?Pushed:\s*work\/w090c\s+[0-9a-f]{7,40}\s+\d+ tests/
  (a real sha + a real test count — the prompt template can never match).

Loop every 90s:
  PUSHED   git ls-remote work/w090c != 385341e... -> flags/w090c_pushed.json
  DONE     real report regex in body            -> flags/w090c_done.json (exit)
  GENERATING body grew / site generating       -> wait
  STALLED   static body, no report             -> continuation message (max 3)
  GONE      tab bounced to /auth               -> outbox + exit (needs TL)
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PUSHED_FLAG = os.path.join(FLAGS, "w090c_pushed.json")
REPORTED_FLAG = os.path.join(FLAGS, "w090c_done.json")

WORKER_CHAT_ID = "1c5e1f29-7a33-4a79-89c7-91d81a7402db"
WORKER_CHAT_URL = "https://chat.z.ai/c/" + WORKER_CHAT_ID
STALE_W090C = "385341eb830110b06b8d2263ede528e7a27d4ffd"
FLEETOS_REMOTE = ("https://x-access-token:%s@github.com/payswapdotorg/"
                  "fleetos.git") % os.environ.get("GITHUB_PAT", "")

CLASSIFY_S = 90
MAX_CONTINUATIONS = 3

REAL_REPORT_RE = (r"W090C COMPLETION REPORT[\s\S]{0,300}?"
                  r"Pushed:\s*work/w090c\s+[0-9a-f]{7,40}\s+\d+\s+tests")

CONTINUATION_MSG = (
    "[TL rescue] Continue the W090C work order autonomously from exactly "
    "where you left off. Do not stop early and do not re-introduce "
    "yourself: finish the remaining screens/journeys, run the three gates "
    "(check / typecheck / bun test), commit, git push origin work/w090c "
    "(the branch on origin is still at the empty starter — your push IS "
    "the deliverable), then end your final message with the exact "
    "'W090C COMPLETION REPORT' block from the work order, with your REAL "
    "commit sha and REAL test counts (never the template placeholders)."
)

CLASSIFY_JS = r"""(() => {
  const txt = document.body.innerText || '';
  const gen = !!(document.querySelector('img[class*=loading], [class*=generating], [role=status]'));
  return JSON.stringify({
    url: location.href,
    generating: gen,
    bodyLength: txt.length,
    composer: !!(document.querySelector('textarea')),
    tail: txt.slice(-200)
  });
})()"""


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def outbox(note):
    os.makedirs(FLAGS, exist_ok=True)
    rec = {"ts": int(time.time()), "from": "resident-td", "note": note}
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log("outbox write failed: %s" % e)


def remote_w090c_sha():
    try:
        r = subprocess.run(["git", "ls-remote", FLEETOS_REMOTE, "work/w090c"],
                           capture_output=True, text=True, timeout=30)
        out = (r.stdout or "").split()
        return out[0].strip() if out else ""
    except Exception:
        return ""


def chat_body_and_state():
    """Full body text + state from the worker tab (opens it if needed)."""
    for t in channel.list_tabs():
        if WORKER_CHAT_ID in (t.get("url") or ""):
            tab = t
            break
    else:
        try:
            tab = channel.new_tab(WORKER_CHAT_URL)
            time.sleep(8)
        except Exception as e:
            log("tab open failed: %s" % e)
            return None, None
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        txt = c.eval("(document.body.innerText || '')", timeout=30) or ""
        st = None
        try:
            v = c.eval(CLASSIFY_JS, timeout=30)
            st = json.loads(v) if v else None
        except Exception:
            pass
        c.close()
        return txt, st
    except Exception as e:
        log("body eval failed: %s" % e)
        return None, None


def send_continuation():
    try:
        res = channel.send_text(CONTINUATION_MSG)
        ok = bool(res.get("ok"))
        log("continuation send ok=%s detail=%s" % (ok, res.get("detail", "")))
        return ok
    except Exception as e:
        log("continuation send error: %s" % e)
        return False


def main():
    os.makedirs(FLAGS, exist_ok=True)
    log("w090c watch armed (corrected classifier: real-report regex)")
    prev_len = -1
    prev_hash = None
    static_rounds = 0
    continuations = 0
    pushed_seen = os.path.exists(PUSHED_FLAG)
    gone_rounds = 0
    while True:
        sha = remote_w090c_sha()
        if sha and sha != STALE_W090C and not pushed_seen:
            pushed_seen = True
            with open(PUSHED_FLAG, "w") as f:
                json.dump({"ts": int(time.time()), "sha": sha}, f)
            outbox("W090C PUSHED: origin work/w090c advanced to %s — "
                   "harvest-ready (TL: clone, re-run gates locally, review, "
                   "merge --no-ff)." % sha[:8])
            log("WORKER PUSHED work/w090c @ %s" % sha[:8])

        txt, st = chat_body_and_state()
        if txt is None:
            log("chat unreadable this round")
            time.sleep(CLASSIFY_S)
            continue

        if re.search(REAL_REPORT_RE, txt):
            with open(REPORTED_FLAG, "w") as f:
                json.dump({"ts": int(time.time()), "pushed_sha": sha}, f)
            m = re.search(r"Pushed:\s*work/w090c\s+([0-9a-f]{7,40})", txt)
            outbox("W090C REAL COMPLETION REPORT detected (claimed sha %s; "
                   "origin shows %s). TL: harvest." % (
                       (m.group(1) if m else "?")[:8], (sha or "unchanged")[:8]))
            log("WORKER DONE (real report). Exiting.")
            return 0

        url = (st or {}).get("url", "") or ""
        if "/auth" in url:
            gone_rounds += 1
            log("worker chat bounced to /auth (round %d)" % gone_rounds)
            if gone_rounds >= 3:
                outbox("W090C worker chat bounced to /auth — the session "
                       "needs the operator/TL in the replay.")
                return 1
        else:
            gone_rounds = 0

        import hashlib
        body_hash = hashlib.sha256(txt.encode(errors="replace")).hexdigest()[:16]
        # the chat UI caps/virtualizes the rendered body: length alone stalls
        # while the worker is mid-run. Content-hash is the true change signal.
        changed = body_hash != prev_hash if prev_hash else True
        grew = len(txt) > prev_len + 40 if prev_len >= 0 else True
        if (st or {}).get("generating") or changed or grew:
            static_rounds = 0
            log("ACTIVE (len=%s hash=%s gen=%s)" % (len(txt), body_hash[:8], (st or {}).get("generating")))
        else:
            static_rounds += 1
            log("static round %d (len=%s)" % (static_rounds, len(txt)))
            if static_rounds >= 2 and continuations < MAX_CONTINUATIONS:
                log("STALLED — sending continuation %d/%d" % (continuations + 1, MAX_CONTINUATIONS))
                if send_continuation():
                    continuations += 1
                    static_rounds = 0
                    outbox("W090C stalled — continuation sent (%d/%d)."
                           % (continuations, MAX_CONTINUATIONS))
        prev_len = len(txt)
        prev_hash = body_hash
        time.sleep(CLASSIFY_S)


if __name__ == "__main__":
    raise SystemExit(main())
