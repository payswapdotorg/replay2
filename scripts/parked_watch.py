#!/usr/bin/env python3
"""parked_watch.py <name> <chat-id> [marker] [prompt-file] — resident watch
for a PARKED (landed-but-unspawned) agents-tab session.

Why this exists (2026-10-02 reset-#17 forensics): a queued agents chat with
zero assistant turns CANNOT be opened in a tab — the SPA bounces /c/<uuid>
back to home until first assistant content exists (verified live: a
completed agents chat cold-loads; the parked sim-c chat bounces). Tab-based
queue_watch therefore cannot own the parked phase. This watcher owns it
server-side (probe_chat.py's in-page fetch — no tab on the chat needed)
and hands off to queue_watch the moment the session spawns.

State machine (CYCLE_S=120):
  PARKED     msgs<=1 and no batch assistant content -> heartbeat + log.
  SPAWNED    assistant activity server-side -> open the chat tab (cold-load
             works once content exists), carry the tab onto the registry
             row (tab-reopen record), launch queue_watch, retire self.
  COMPLETE   reportInAssistant in the probe -> write
             flags/<name>-complete.marker + outbox note, retire self.
  LOST       probe says chat dead/not-found -> bounded void + re-dispatch
             with the SAME packet (dispatch_worker.create) — max
             REDISPATCH_MAX per watcher lifetime.
  MORNING    parked through the §8 reset window's first 90 min (window
             opens 05:38Z) with no spawn -> ONE void + fresh re-dispatch
             per day (the W121 morning-daemon law: a chat that sat queued
             a full day gets one fresh landing INSIDE the open window),
             max MORNING_MAX total. Needs the prompt-file arg.

Supervisor contract: flags/parked_watch.spec.<name> (this script writes it;
supervisor.py's ensure_parked_watch resurrects this watcher while the spec
exists). Heartbeat: flags/parked_watch_heartbeat.<name>. Retire = spec
removed. Log: /tmp/parked_watch_<name>.log (via launch_parked_watch.py).
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402
import dispatch_worker as dw  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")

CYCLE_S = 120
PROBE_TIMEOUT = 90
# §8 reset window (multi-day observed doctrine): daily quota resets
# 05:38Z-09:36Z. A parked chat gets one fresh landing inside the window.
WIN_OPEN_H, WIN_OPEN_M = 5, 38
WIN_CLOSE_H, WIN_CLOSE_M = 9, 36
MORNING_DELAY_M = 90          # act this far INTO the window (let the queue move first)
MORNING_MAX = 2               # total morning re-dispatches per watcher lifetime
REDISPATCH_MAX = 2            # total LOST-path re-dispatches


def log(name, m):
    print(f"[{name} {time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {m}", flush=True)


def heartbeat(name):
    try:
        open(os.path.join(FLAGS, f"parked_watch_heartbeat.{name}"), "w").write(str(int(time.time())))
    except Exception:
        pass


def outbox(name, note):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time()), "name": name, "note": note}) + "\n")
    except Exception:
        pass


def write_spec(name, chat_id, marker, prompt_file):
    spec = {"name": name, "chat_id": chat_id, "marker": marker,
            "prompt_file": prompt_file, "pid": os.getpid(), "ts": int(time.time())}
    open(os.path.join(FLAGS, f"parked_watch.spec.{name}"), "w").write(json.dumps(spec) + "\n")


def probe(chat_id, marker):
    """Server-side truth via probe_chat.py (in-page fetch from any
    chat.z.ai tab). Returns dict or None on tooling failure."""
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(BASE, "probe_chat.py"), chat_id, marker],
            cwd=BASE, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
        line = (r.stdout or "").strip().split("\n")[-1]
        return json.loads(line)
    except Exception as e:
        log(chat_id[:8], f"probe tooling failure: {type(e).__name__} {str(e)[:60]}")
        return None


def live_chat_id(name):
    """The live registry row's chat uuid (re-resolved after re-dispatches)."""
    rec = dw._find(name)
    if not rec:
        return None
    m = re.search(r"/c/([0-9a-f-]{36})", rec.get("url") or "")
    return m.group(1) if m else None


def register_row(name, chat_id, prompt_file, prompt_chars):
    """Idempotent re-registration of a landed server-side session after a
    reset (reopen_and_watch.py pattern, queued-capacity semantics: the
    prompt landed; generation starts when the platform's queue moves)."""
    if dw._find(name):
        return
    dw._save({"name": name, "tab_id": "", "url": f"https://chat.z.ai/c/{chat_id}",
              "ts": int(time.time()), "prompt_file": prompt_file,
              "prompt_chars": prompt_chars, "mode": "agents-tab", "model": "GLM-5.3",
              "skill": "Full-Stack", "insert_pct": 100, "sent": True,
              "stage": "queued-capacity",
              "note": "reset re-registration of landed server-side session"})


def open_chat_tab(chat_id):
    """Cold-load the chat in a fresh tab. Only works once assistant content
    exists (the SPA bounce law) — retry-safe: returns tab dict or None."""
    try:
        tab = channel.new_tab(f"https://chat.z.ai/c/{chat_id}")
        if not tab:
            return None
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            c.call("Page.navigate", {"url": f"https://chat.z.ai/c/{chat_id}"}, timeout=25)
            time.sleep(6)
            for t in channel.list_tabs():
                if t.get("id") == tab.get("id") and chat_id[:8] in (t.get("url") or ""):
                    return t
            return None
        finally:
            c.close()
    except Exception:
        return None


def handoff(name, chat_id, marker):
    """SPAWNED path: open the tab, carry it onto the registry row, hand the
    lane to queue_watch (which writes its own supervisor spec)."""
    tab = open_chat_tab(chat_id)
    if not tab:
        log(name, "spawn detected but chat tab did not open — retrying next cycle")
        return False
    dw._save({"name": name, "action": "tab-reopen", "tab_id": tab["id"],
              "ts": int(time.time()), "note": "parked_watch handoff tab"})
    outbox(name, f"SPAWNED: chat {chat_id[:8]} has assistant activity — queue_watch takes over")
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE, "launch_queue_watch.py"),
                            name, tab["id"][:8], marker],
                           capture_output=True, text=True, timeout=120)
        log(name, "queue_watch launched: " + ((r.stdout or "").strip() or "no-output")[:80])
    except Exception as e:
        log(name, f"launch_queue_watch failed: {e} — supervisor will not own this lane; keeping server-side watch")
        return "watch-on"
    return True


def redispatch(name, reason, prompt_file):
    """Void + fresh create with the SAME packet (the proven assault path).
    Returns the new chat id or None."""
    if not prompt_file or not os.path.isfile(prompt_file):
        log(name, f"re-dispatch skipped ({reason}): no prompt file")
        return None
    subprocess.run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                    "void", name, reason], capture_output=True, text=True, timeout=120)
    r = subprocess.run([sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                        "create", name, prompt_file],
                       capture_output=True, text=True, timeout=1800)
    tail = "\n".join((r.stdout or "").strip().split("\n")[-3:])
    log(name, f"re-dispatch rc={r.returncode}: {tail[:200]}")
    return live_chat_id(name)


def in_morning_window(now=None):
    t = time.gmtime(now or time.time())
    cur = t.tm_hour * 60 + t.tm_min
    return (WIN_OPEN_H * 60 + WIN_OPEN_M + MORNING_DELAY_M) <= cur <= (WIN_CLOSE_H * 60 + WIN_CLOSE_M)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    name = sys.argv[1]
    chat_id = sys.argv[2]
    marker = sys.argv[3] if len(sys.argv) > 3 else "COMPLETION REPORT"
    prompt_file = os.path.abspath(sys.argv[4]) if len(sys.argv) > 4 else ""

    os.makedirs(FLAGS, exist_ok=True)
    register_row(name, chat_id, prompt_file,
                 len(open(prompt_file, encoding="utf-8").read()) if prompt_file and os.path.isfile(prompt_file) else 0)
    write_spec(name, chat_id, marker, prompt_file)
    log(name, f"armed on chat {chat_id[:12]} marker='{marker}' prompt={'yes' if prompt_file else 'NO (re-dispatch disabled)'}")

    parked_since = int(time.time())
    morning_actions = 0
    lost_redispatches = 0
    last_morning_day = ""
    while True:
        heartbeat(name)
        p = probe(chat_id, marker)
        if p is None:
            time.sleep(CYCLE_S)
            continue
        # discriminate: chat DEAD server-side (http-404/400) vs TOOLING
        # failure (no tab / 5xx / exception) — the latter must never burn a
        # re-dispatch (the "no chat.z.ai tab" lesson: browser flakiness is
        # not chat death)
        err = str(p.get("err") or "")
        chat_dead = (p.get("alive") is False) or ("404" in err) or ("400" in err) or ("not found" in err.lower())
        if err and not chat_dead:
            log(name, f"probe tooling failure ({err[:60]}) — retrying next cycle")
            time.sleep(CYCLE_S)
            continue
        if chat_dead:
            lost_redispatches += 1
            if lost_redispatches > REDISPATCH_MAX:
                log(name, "chat lost and re-dispatch budget exhausted — flagging for the TL")
                outbox(name, f"LOST: chat {chat_id[:8]} dead; re-dispatch budget exhausted")
                open(os.path.join(FLAGS, f"{name}-lost.flag"), "w").write(str(int(time.time())))
                return 3
            log(name, f"chat not found — void + re-dispatch ({lost_redispatches}/{REDISPATCH_MAX})")
            new_id = redispatch(name, "parked_watch: chat lost server-side", prompt_file)
            if new_id:
                chat_id = new_id
                write_spec(name, chat_id, marker, prompt_file)
            time.sleep(CYCLE_S)
            continue
        # spawn / completion discrimination (agents chats: real content lives
        # in the batch store; history holds the prompt + an empty stub)
        spawned = int(p.get("msgs") or 0) > 1 or int((p.get("batch") or {}).get("assistantish") or 0) > 0
        if p.get("reportInAssistant"):
            open(os.path.join(FLAGS, f"{name}-complete.marker"), "w").write(f"{time.time()} {chat_id}\n")
            outbox(name, f"COMPLETE: report marker in assistant content (chat {chat_id[:8]}) — TL harvest due")
            log(name, "COMPLETE — marker written; retiring")
            try:
                os.remove(os.path.join(FLAGS, f"parked_watch.spec.{name}"))
            except Exception:
                pass
            return 0
        if spawned:
            rc = handoff(name, chat_id, marker)
            if rc is True:
                try:
                    os.remove(os.path.join(FLAGS, f"parked_watch.spec.{name}"))
                except Exception:
                    pass
                log(name, "handed off to queue_watch — retiring")
                return 0
            if rc == "watch-on":
                # queue_watch launch failed: keep server-side watch (probe
                # still discriminates completion below)
                pass
            time.sleep(CYCLE_S)
            continue
        # PARKED: morning law — one fresh landing per day inside the window
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if (in_morning_window() and last_morning_day != today
                and morning_actions < MORNING_MAX and prompt_file):
            parked_h = (time.time() - parked_since) / 3600.0
            if parked_h >= 6:   # only for chats that sat queued a long stretch
                # race guard: re-probe immediately before voiding — a chat
                # that spawned seconds after the cycle probe must never be
                # killed by the morning action
                p2 = probe(chat_id, marker)
                if p2 and not p2.get("err") and (
                        int(p2.get("msgs") or 0) > 1
                        or int((p2.get("batch") or {}).get("assistantish") or 0) > 0):
                    log(name, "MORNING aborted — chat spawned between probes")
                    continue
                last_morning_day = today
                morning_actions += 1
                log(name, f"MORNING: parked {parked_h:.1f}h through window open — void + fresh landing ({morning_actions}/{MORNING_MAX})")
                outbox(name, f"MORNING-REDISPATCH: parked {parked_h:.1f}h, no spawn — fresh landing inside the reset window")
                new_id = redispatch(name, "morning law: parked a full day, no spawn", prompt_file)
                if new_id:
                    chat_id = new_id
                    write_spec(name, chat_id, marker, prompt_file)
                    parked_since = int(time.time())
        log(name, f"parked msgs={p.get('msgs')} batch={p.get('batch')}")
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    sys.exit(main())
