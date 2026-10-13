#!/usr/bin/env python3
"""ws_reaper.py — standing stale-workspace reaper (2026-10-13, post-drought).

FORENSICS (2026-10-13 01:07-08:27Z, 7.3h admission drought): the account's
sandbox-workspace limit is 3 (GET /api/v1/web-dev/workspaces/user-fc ->
{"limit":3,...}). After every merge+harvest the worker's workspace lingers
as is_active:true — boot prompt §16(a) documented the doctrine ("completed
sessions' sandboxes linger and hold the usage limit — release them") but
NOTHING automated it, and three delivered workspaces (PCR-002/PCR-003/
PCS-002, all merged) silently filled 3/3. Every subsequent agent-session
generation start was rejected at the workspace gate (completions POST ->
"HTTP status Error: 0"), so PCS-003 sat never-admitted across three
dispatches while queue_watch burned zombie voids + assaults on a condition
none of its ladder could cure. The Lead freed the slots manually
(tl_delete_ws) and the very next dispatch admitted in 2 seconds.

THIS daemon makes the fix standing. Every CHECK_INTERVAL it:
  1. lists held workspaces (Bearer token from flags/chat_token — no CDP,
     no browser dependency, safe from tab wedges);
  2. for each workspace's chat, probes the server-side message tree for a
     FILLED completion report (marker + real hex SHA within the report
     body — the queue_watch filled-gate family, EN + 完成报告);
  3. releases a workspace ONLY when ALL hold:
       - the chat has a filled report (deliverable durable: the work-order
         protocol pushes the branch BEFORE reporting, so GitHub holds the
         work regardless);
       - the chat has been STATIC for >= GRACE (default 5400s = 90 min —
         far beyond the Lead's post-report harvest step, which typically
         lands within minutes; nudges/turns reset the clock);
       - no hold flag: flags/ws_reaper.hold.<chat-id> (the Lead can pin
         any workspace, e.g. mid-forensics);
       - the chat has >= 2 messages (a report implies an assistant turn);
  4. releases at most ONE workspace per cycle (rate-limited teardown: a
     logic bug can never nuke the whole set in one sweep, and the audit
     trail stays readable);
  5. writes flags/ws_reaper_heartbeat + logs to /tmp/ws_reaper.log.

Never touches: chats without reports (in-flight workers), regular chats
(they hold no workspace), the operator console (not a workspace).

Deliberately NOT in the immortality ring (no CDP, ~1 HTTP call/min-class,
unattractive OOM target); a sandbox reset re-bootstraps it from the
worklog like every other resident tool.

Usage: nohup setsid python3 ws_reaper.py >/dev/null 2>&1 &
Env: WS_REAPER_INTERVAL (s, default 600), WS_REAPER_GRACE (s, default
     5400), WS_REAPER_DRY=1 (log-only, no deletions).
"""
import json
import os
import re
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

FLAGS = os.path.join(BASE, "flags")
TOKEN_PATH = os.path.join(FLAGS, "chat_token")
HB_PATH = os.path.join(FLAGS, "ws_reaper_heartbeat")
LOG_PATH = "/tmp/ws_reaper.log"

INTERVAL = int(os.environ.get("WS_REAPER_INTERVAL", "600"))
GRACE = int(os.environ.get("WS_REAPER_GRACE", "5400"))
DRY = os.environ.get("WS_REAPER_DRY", "") == "1"

# filled-report gate (queue_watch family, simplified but hex-anchored):
# a report marker whose body carries a real hex SHA (7-40) near a
# base/branch/pushed label — prompt echoes carry placeholders, never hex.
FILLED = [
    re.compile(r"===?\s*[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
               r"[\s\S]{0,900}?(?:base\s*branch|基础分支)[^\n]{0,60}?(?:base\s*SHA|基础\s*SHA)\s*[:：]\s*(?:main|主干)\s*@\s*[0-9a-f]{7,40}",
               re.IGNORECASE),
    re.compile(r"===?\s*[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
               r"[\s\S]{0,300}?(?:Base\s*SHA|基础\s*SHA)\s*[:：]\s*(?:main\s*@?\s*)?[0-9a-f]{40}",
               re.IGNORECASE),
    re.compile(r"===?\s*[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\s*(?:COMPLETION\s*REPORT|完成报告)\s*===?"
               r"[\s\S]{0,900}?(?:Branch\s*SHA\s*pushed|分支\s*SHA|推送的\s*分支|tarball)[^\n]{0,80}?[0-9a-f]{7,40}",
               re.IGNORECASE),
]


def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def heartbeat():
    try:
        with open(HB_PATH, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def token():
    return open(TOKEN_PATH).read().strip().strip('"')


def api(path, method="GET", timeout=20):
    rq = urllib.request.Request("https://chat.z.ai" + path,
                                headers={"Authorization": "Bearer " + token()})
    rq.get_method = lambda: method
    with urllib.request.urlopen(rq, timeout=timeout) as r:
        return json.loads(r.read().decode())


def workspaces():
    d = api("/api/v1/web-dev/workspaces/user-fc")
    items = d.get("workspaces") if isinstance(d, dict) else None
    if items is None and isinstance(d, dict):
        v = d.get("data", d)
        for k in ("workspaces", "list", "items"):
            if isinstance(v, dict) and isinstance(v.get(k), list):
                items = v[k]
                break
    return items or []


def chat_state(cid):
    """(n_msgs, last_ts, filled_report) for a chat; None on probe failure
    (uncertainty NEVER releases)."""
    try:
        j = api("/api/v1/chats/" + cid)
        chat = j.get("chat") or {}
        if isinstance(chat.get("chat"), dict):   # nested shape
            chat = chat["chat"]
        msgs = ((chat.get("history") or {}).get("messages")) or {}
        vals = list(msgs.values()) if isinstance(msgs, dict) else list(msgs)
        if not vals:
            return None
        last_ts = max((m.get("timestamp") or 0) for m in vals)
        filled = False
        for m in vals:
            if (m.get("role") or "assistant") == "user":
                continue
            txt = m.get("content") or ""
            if any(rx.search(txt) for rx in FILLED):
                filled = True
                break
        return len(vals), last_ts, filled
    except Exception:
        return None


def release(cid):
    for form in (cid, "chat-" + cid):
        rq = urllib.request.Request(
            "https://chat.z.ai/api/v1/web-dev/workspaces/" + form,
            headers={"Authorization": "Bearer " + token()})
        rq.get_method = lambda: "DELETE"
        try:
            with urllib.request.urlopen(rq, timeout=20) as r:
                body = r.read().decode()[:200]
                log("RELEASE %s -> %s %s" % (form, r.status, body))
                return True
        except Exception as e:
            log("release %s failed: %r" % (form, e))
    return False


def cycle():
    heartbeat()
    try:
        held = workspaces()
    except Exception as e:
        log("workspace list failed: %r" % e)
        return
    if not held:
        log("held=0 — clean")
        return
    log("held=%d: %s" % (len(held), ", ".join(
        str(w.get("chat_id"))[5:17] for w in held)))
    now = time.time()
    for w in held:
        cid = str(w.get("chat_id") or "").removeprefix("chat-")
        if not cid or len(cid) < 30:
            continue
        if os.path.exists(os.path.join(FLAGS, "ws_reaper.hold." + cid)):
            log("  %s HOLD flag — skipping" % cid[:12])
            continue
        st = chat_state(cid)
        if st is None:
            log("  %s probe UNCERTAIN — skipping (never release on uncertainty)" % cid[:12])
            continue
        n, last_ts, filled = st
        static = now - last_ts
        if n < 2 or not filled:
            log("  %s n=%d filled=%s — IN-FLIGHT/NO-REPORT, skipping" % (cid[:12], n, filled))
            continue
        if static < GRACE:
            log("  %s report filled but static only %ds/%ds — grace, skipping" % (
                cid[:12], int(static), GRACE))
            continue
        log("  %s STALE-DELIVERED (n=%d, static=%ds, report filled) — releasing" % (
            cid[:12], n, int(static)))
        if DRY:
            log("  DRY-RUN: would DELETE workspace for %s" % cid[:12])
        else:
            release(cid)
        return   # at most ONE release per cycle


def main():
    log("ws_reaper started (interval=%ds grace=%ds dry=%s)" % (INTERVAL, GRACE, DRY))
    while True:
        try:
            cycle()
        except Exception as e:
            log("cycle error: %r" % e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
