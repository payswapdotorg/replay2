#!/usr/bin/env python3
"""stall_recovery.py — dead-turn detector + recovery trigger (R11 'nudge'
concept, redesigned 2026-09-12 after the rwo-001/002 forensic).

FORENSIC BACKGROUND (2026-09-12 12:00-13:08, both remediation workers):
- A worker turn can start (assistant message created, DOM renders commands
  + file reads) and then die mid-stream server-side. The UI then sits in
  'turn open' mode FOREVER: the composer accepts typing but form submits
  are silently swallowed (React handler gated on generation state), there
  is no Stop button, and the API shows the assistant message with len=0
  (content only persists at stream END — so a live generating turn ALSO
  shows len=0; the discriminator is DOM progress over time).
- queue_watch classifies such a session as plain 'queued' (no capacity
  text, no Stop button) — and plain 'queued' NEVER gets assaulted, so the
  dead turn would sit forever. This loop closes that gap.

RECOVERY MECHANISM: close the session's tab. queue_watch then sees
'tablost' on its next poll and runs its own designed void+assault path
(fresh re-dispatch). We never touch the chat API for writes and never
click anything inside the page.

STALL SIGNATURE (ALL must hold, checked every cycle):
1. tab exists (prefix from a queue_watch spec), URL is /c/<chat-id>
2. DOM body length UNCHANGED for >= STALL_AFTER seconds (sampled each cycle)
3. server API last message is an assistant turn with len=0
   (open turn, nothing committed — a completed turn would have content)
4. body shows NO wait-state markers ('at capacity', 'peak hours',
   'personal limit', 'try again 1 hour later') — those belong to
   queue_watch's ride-out policies
5. no completion marker for the session yet
   (a stale-render DONE session is NOT ours to touch — manual R20 path)

BOUNDS: at most MAX_RECOVERIES_PER_HOUR per session (churn protection);
never closes a tab twice within COOLDOWN seconds.
"""

import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

FLAGS = os.path.join(BASE, "flags")
LOGDIR = os.path.join(BASE, "logs")
HEARTBEAT = os.path.join(FLAGS, "stall_recovery_heartbeat")
RECOVERED_LOG = os.path.join(FLAGS, "stall_recovery.recovered")

STALL_AFTER = 1800          # 30 min of frozen DOM + open empty assistant turn
CYCLE = 120                 # poll every 2 min
MAX_RECOVERIES_PER_HOUR = 3
WAIT_MARKERS = ("at capacity", "peak hours", "personal limit",
                "try again 1 hour later")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        os.makedirs(LOGDIR, exist_ok=True)
        with open(os.path.join(LOGDIR, "stall_recovery.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def heartbeat():
    try:
        with open(HEARTBEAT, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def load_specs():
    """Active queue_watch sessions: {name: tab_prefix}."""
    import glob as _glob
    out = {}
    for p in _glob.glob(os.path.join(FLAGS, "queue_watch.spec.*")):
        try:
            d = json.loads(open(p).read().strip() or "{}")
            if d.get("name") and d.get("tab_prefix"):
                out[d["name"]] = d["tab_prefix"]
        except Exception:
            continue
    return out


def recovered_counts():
    """{session_name: [(epoch, tab_id), ...]} from the recovery log."""
    out = {}
    try:
        for line in open(RECOVERED_LOG, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                ts, name, tab = line.split("\t")
                out.setdefault(name, []).append((float(ts), tab))
            except Exception:
                continue
    except Exception:
        pass
    return out


def count_recent(recs, name, window=3600):
    now = time.time()
    return sum(1 for ts, _ in (recs.get(name) or []) if now - ts < window)


def api_messages(cdp, chat_id):
    """Server-side message list via in-page fetch (same-origin, cookies)."""
    js = f"""(async () => {{
      try {{
        const r = await fetch('/api/v1/chats/{chat_id}', {{credentials: 'include'}});
        if (!r.ok) return JSON.stringify({{err: 'http' + r.status}});
        const j = await r.json();
        const msgs = Object.values((j.chat || {{}}).history || {{}}).messages || {{}};
        const out = Object.values(msgs).map(m => ({{
          role: m.role, ts: m.timestamp || 0, len: (m.content || '').length
        }}));
        out.sort((a, b) => a.ts - b.ts);
        return JSON.stringify(out);
      }} catch (e) {{
        return JSON.stringify({{err: String(e).slice(0, 80)}});
      }}
    }})()"""
    res = cdp.eval(js, await_promise=True, timeout=25)
    try:
        return json.loads(res or "[]")
    except Exception:
        return [{"err": "parse"}]


def find_tab(prefix):
    for t in channel.list_tabs():
        if t["id"].startswith(prefix):
            return t
    return None


def close_tab(tab_id):
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:9222/json/close/{tab_id}", timeout=6).read()
        return True
    except Exception:
        return False


def main():
    log("stall_recovery online — dead-turn detector (frozen DOM + open "
        "empty assistant turn -> tab close -> queue_watch assault)")
    dom_len = {}   # name -> (epoch, body_len, tab_id)
    while True:
        try:
            heartbeat()
            specs = load_specs()
            recs = recovered_counts()
            for name, prefix in sorted(specs.items()):
                if os.path.exists(os.path.join(FLAGS, f"{name}-complete.marker")):
                    continue
                tab = find_tab(prefix)
                if not tab:
                    dom_len.pop(name, None)
                    continue
                try:
                    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
                    try:
                        url = cdp.eval("location.href", timeout=12) or ""
                        body = cdp.eval("document.body.innerText || ''",
                                        timeout=20) or ""
                    finally:
                        cdp.close()
                except Exception:
                    continue
                if "/c/" not in url:
                    dom_len.pop(name, None)
                    continue
                low = body.lower()
                if any(m in low for m in WAIT_MARKERS):
                    # queue/rate-limit state — queue_watch's jurisdiction
                    dom_len.pop(name, None)
                    continue
                blen = len(body)
                prev = dom_len.get(name)
                if prev is None or prev[1] != blen or prev[2] != tab["id"]:
                    dom_len[name] = (time.time(), blen, tab["id"])
                    continue
                frozen_for = time.time() - prev[0]
                if frozen_for < STALL_AFTER:
                    continue
                # frozen long enough — is the server-side turn open+empty?
                try:
                    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
                    try:
                        chat_id = url.rstrip("/").split("/c/")[-1].split("?")[0]
                        msgs = api_messages(cdp, chat_id)
                    finally:
                        cdp.close()
                except Exception:
                    continue
                if not msgs or "err" in (msgs[-1] if msgs else {}):
                    continue
                last = msgs[-1]
                is_open_empty = (last.get("role") == "assistant"
                                 and int(last.get("len", 0)) == 0)
                if not is_open_empty:
                    # turn completed server-side (stale-render DONE) or never
                    # started (queued) — NOT ours to touch
                    log(f"{name}: frozen DOM {int(frozen_for)}s but last "
                        f"server msg role={last.get('role')} len={last.get('len')} "
                        f"— leaving to queue_watch (stale-render DONE needs the "
                        f"manual fresh-tab path)")
                    dom_len[name] = (time.time(), blen, tab["id"])
                    continue
                if count_recent(recs, name) >= MAX_RECOVERIES_PER_HOUR:
                    log(f"{name}: stall detected but recovery budget exhausted "
                        f"— leaving tab (manual review needed)")
                    dom_len[name] = (time.time(), blen, tab["id"])
                    continue
                # RECOVER: close the tab; queue_watch assault re-dispatches
                ok = close_tab(tab["id"])
                log(f"{name}: DEAD TURN (frozen {int(frozen_for)}s, assistant "
                    f"msg open+empty since ts={last.get('ts')}) — closing tab "
                    f"{tab['id'][:8]} (ok={ok}) -> queue_watch assault")
                if ok:
                    with open(RECOVERED_LOG, "a") as f:
                        f.write(f"{time.time()}\t{name}\t{tab['id']}\n")
                dom_len.pop(name, None)
        except Exception as e:
            log(f"cycle error {e!r} — continuing")
        time.sleep(CYCLE)


if __name__ == "__main__":
    main()
