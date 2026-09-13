#!/usr/bin/env python3
"""post_reset_login_sentinel.py — resumes the CURRENT roadmap after the
2026-09-13 ~17:40 UTC sandbox reset (lesson-58 recovery, round 3).

Pre-reset roadmap state (from conversation context + origin truth):
  codex main @ d304e2043 = 2/12 RWOs merged (RWO-003 #33, RWO-004 #34).
  RWO-001 branch pushed @ d003b025e (309/309 protocol green; 3 app-server
  test failures routed to the rwo-001-fix worker).
  Live worker sessions pre-reset (server-side, SAME account):
    rwo-001-fix  -> chat 7b471592 (prompt sent 12:14, turn froze mid-stream)
    rwo-007      -> chat 2d141d70 (prompt sent 12:26, queued, never fired)
    vwo-011      -> chat b9ae31c5 (prompt sent ~12:31, froze at 12.9k chars)
  Account was under a usage-cap treadmill; last re-arm ~16:23 UTC.

On login (read-only DOM probe, 45s cadence, never sends):
  1. verify the three chats still exist via /api/v1/chats/list;
  2. re-register the live ones in flags/session_registry.jsonl (tab-reopen
     style records so queue_watch can aim at them);
  3. arm one queue_watch per session (COMPLETION REPORT markers);
  4. if a chat is gone server-side -> void record -> fresh dispatch via
     dispatch_worker create (assault machinery);
  5. log everything; exit when all three slots are armed.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
LOG = open(os.path.join(BASE, "logs", "post_reset_sentinel.log"), "a", buffering=1)
HB = os.path.join(FLAGS, "post_reset_sentinel_heartbeat")

# name -> (chat-id-prefix, marker, prompt file)
PLAN = {
    "rwo-001-fix": ("7b471592", "COMPLETION REPORT",
                    os.path.join(BASE, "worker-prompts", "RWO-001-FIX.md")),
    "rwo-007":     ("2d141d70", "COMPLETION REPORT",
                    os.path.join(BASE, "worker-prompts", "RWO-007.md")),
    "vwo-011":     ("b9ae31c5", "COMPLETION REPORT",
                    os.path.join(BASE, "worker-prompts", "VWO-011.md")),
}


def log(msg):
    LOG.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")


def hb():
    try:
        with open(HB, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def logged_in():
    """Read-only DOM probe of any chat.z.ai tab."""
    try:
        t = channel.find_tab("chat.z.ai")
        if not t:
            return False
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
        try:
            txt = c.eval("(document.body.innerText || '')") or ""
            return ("Sign in" not in txt) and ("Log in" not in txt) and len(txt) > 300
        finally:
            c.close()
    except Exception:
        return False


def chats_list_ids():
    """Server-side chat ids via in-page fetch (read-only)."""
    t = channel.find_tab("chat.z.ai")
    if not t:
        return None
    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=45)
    try:
        raw = c.eval("""
        (async () => {
          const r = await fetch('/api/v1/chats/list', {credentials:'include'});
          const j = await r.json();
          return JSON.stringify(j);
        })()""", await_promise=True, timeout=45)
        d = json.loads(raw)
        items = d.get("data", d) if isinstance(d, dict) else d
        if isinstance(items, dict):
            for k in ("chatList", "chats", "items", "list"):
                if k in items and isinstance(items[k], list):
                    items = items[k]
                    break
        out = []
        if isinstance(items, list):
            for c2 in items:
                cid = str(c2.get("id") or c2.get("chatId") or c2.get("uuid") or "")
                if cid:
                    out.append(cid)
        return out
    finally:
        c.close()


def register_reopen(name, chat_id):
    """Open a REAL tab at the chat URL (queue_watch resolves tabs by id
    prefix — the spec needs a live tab, not a placeholder) and register."""
    tab = channel.new_tab()
    if not tab:
        log(f"{name}: could not open tab for {chat_id}")
        return None
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        c.call("Page.navigate", {"url": f"https://chat.z.ai/c/{chat_id}"}, timeout=30)
        time.sleep(6)
    finally:
        c.close()
    rec = {
        "name": name,
        "tab_id": tab["id"],
        "url": f"https://chat.z.ai/c/{chat_id}",
        "ts": int(time.time()),
        "prompt_file": PLAN[name][2],
        "mode": "agents-tab",
        "model": "GLM-5.3",
        "skill": "Full-Stack",
        "note": "post-reset re-registration of surviving server-side session",
    }
    with open(REG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def arm_watcher(name, marker, tab_prefix):
    # write the supervisor-contract spec; supervisor relaunches queue_watch
    spec = os.path.join(FLAGS, f"queue_watch.spec.{name}")
    with open(spec, "w") as f:
        f.write(json.dumps({"name": name, "tab_prefix": tab_prefix,
                            "marker": marker, "prompt_file": PLAN[name][2]}) + "\n")
    log(f"armed watcher spec for {name} (supervisor will relaunch <=10s)")


def main():
    log("post-reset sentinel online — waiting for operator chat.z.ai login")
    waited = 0
    while waited < 6 * 3600:
        hb()
        if logged_in():
            log("LOGIN DETECTED — resuming roadmap")
            break
        time.sleep(45)
        waited += 45
    else:
        log("6h elapsed without login — exiting (operator absent)")
        return 1
    # allow the SPA a moment post-login
    time.sleep(20)
    ids = chats_list_ids() or []
    log(f"server-side chats visible: {len(ids)}")
    for name, (prefix, marker, pf) in PLAN.items():
        hb()
        match = next((cid for cid in ids if cid.startswith(prefix)), None)
        if match:
            log(f"{name}: chat {match} SURVIVED — re-registering + arming watcher")
            rec = register_reopen(name, match)
            if rec:
                arm_watcher(name, marker, rec["tab_id"][:8])
        else:
            log(f"{name}: chat gone server-side — fresh dispatch")
            # void-marker then create (assault machinery)
            with open(REG, "a") as f:
                f.write(json.dumps({"action": "void", "name": name,
                                    "reason": "chat absent after sandbox reset",
                                    "ts": int(time.time())}) + "\n")
            if os.path.exists(pf):
                r = subprocess.run([sys.executable,
                                    os.path.join(BASE, "dispatch_worker.py"),
                                    "create", name, pf],
                                   capture_output=True, text=True, timeout=1800)
                log(f"{name}: create rc={r.returncode} tail="
                    f"{(r.stdout or '').strip()[-200:]}")
                arm_watcher(name, marker, "AUTO")
            else:
                log(f"{name}: NO PROMPT FILE — cannot dispatch")
    log("all slots handled — sentinel exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
