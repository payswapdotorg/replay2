#!/usr/bin/env python3
"""ppr022_composer_loop.py — composer-path turn spawner for the PPR-022 r4 worker.

2026-10-01 night-shift law (proven live): on this platform-distress night,
- raw-completions (api_resume) turns are TOOL-LESS (the model writes command
  text; no agent runtime attached) — useless for real work;
- composer sends on a POLLUTED tree often null-commit — but they still
  SPAWN tool-ed agent turns (65ac45b2: 50 blocks, closed GAP A);
- a work-rich chat tab needs ~10-15 min of paint before its composer is
  drivable (§11a wedge law) — send too early and the driver's evals time out.

Loop: wait-for-paint -> dispatch send nudge -> watch batch growth -> on turn
death: close tab, fresh tab, repeat. Stop on the completion-report marker.

Launch: dfork_launch.py /tmp/ppr022_composer.log <py> ppr022_composer_loop.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATE = os.path.join(FLAGS, "ppr023_composer_state.json")
CDP = "http://127.0.0.1:9222"

CHAT = "02f9e953-423c-4f25-a199-cb06b8fe1262"
URL = f"https://chat.z.ai/c/{CHAT}"
SESSION = "ppr023-r1"
REPORT_MARK = "=== PPR-023 COMPLETION REPORT ==="
MAX_CYCLES = 25
PAINT_TIMEOUT_S = 1500       # 25 min max wait for tab paint
PAINT_POLL_S = 30
TURN_WATCH_S = 1800          # 30 min max per turn
TURN_POLL_S = 60
STATIC_REFIRE = 8            # ~8 min no growth => turn dead

NUDGE = (
    "[SYSTEM — resident watcher] Your previous turn was interrupted by a "
    "platform capacity event; the dead turn has been closed cleanly and your "
    "pod, files, and branch commits are intact — nothing was lost. Continue "
    "the PPR-023 (OpenClaw) work order from exactly where you left off "
    "(you were debugging the certified-run preload: the loader hook breaking "
    "resolution of @openclaw/normalization-core — check the pnpm install "
    "state vs the isolated no-preload entry). Do NOT redo completed work; "
    "cheaply re-verify the in-flight step, then finish the certified run + "
    "evidence, complete the gate battery honestly, build the delivery "
    "tarball, append the worklog, and emit your FINAL message: "
    "=== PPR-023 COMPLETION REPORT === ... === END REPORT === exactly per "
    "the work-order contract (report only AFTER the gates actually ran)."
)


def log(m):
    print(f"[{time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {m}", flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def state(d):
    d["ts"] = int(time.time() * 1000)
    try:
        json.dump(d, open(STATE, "w"), indent=1)
    except Exception:
        pass


def tabs():
    with urllib.request.urlopen(CDP + "/json/list", timeout=10) as r:
        return json.load(r)


def close_chat_tabs(keep_responsive=True):
    """2026-10-01 paint-economy law: close only WEDGED chat tabs; a
    responsive tab is precious (paints of the growing chat take 10-30 min)
    — reuse it for the next send instead of re-painting from scratch."""
    kept = None
    for t in tabs():
        if CHAT in (t.get("url") or ""):
            if keep_responsive and paint_ok(t["id"]):
                kept = t
                continue
            try:
                urllib.request.urlopen(f"{CDP}/json/close/{t['id']}", timeout=8)
            except Exception:
                pass
    return kept


def fresh_tab():
    req = urllib.request.Request(f"{CDP}/json/new?{URL}", method="PUT")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def paint_ok(tab_id):
    """bodyLen>2500 and a fast eval == painted and drivable."""
    try:
        import websocket
        tgt = next((t for t in tabs() if t["id"] == tab_id), None)
        if not tgt:
            return False
        ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=12)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": "document.body.innerText.length", "returnByValue": True}}))
        r = json.loads(ws.recv())
        ws.close()
        v = r.get("result", {}).get("result", {}).get("value")
        return isinstance(v, int) and v > 2500
    except Exception:
        return False


def wait_paint(tab_id):
    t0 = time.time()
    while time.time() - t0 < PAINT_TIMEOUT_S:
        if paint_ok(tab_id):
            return True
        time.sleep(PAINT_POLL_S)
    return False


def _api_eval(js, timeout=60):
    """fetch-based API call from any chat.z.ai tab; returns parsed JSON (dict passthrough)."""
    import channel
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        v = ws.eval(js, await_promise=True, timeout=timeout)
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str) and v[:1] in ("{", "["):
            return json.loads(v)
        return v
    finally:
        try:
            ws.close()
        except Exception:
            pass


def stop_cure():
    """One §8 stop/continue round: close any held turn slot. Idempotent —
    if nothing is held the stop is a no-op and continue still 410s."""
    js = """(async () => {
      const t = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
      const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store',
        headers: {'Authorization': 'Bearer ' + t}});
      if (!r.ok) return {err: 'http-' + r.status};
      const j = await r.json();
      const mid = ((j.chat || {}).history || {}).currentId;
      if (!mid) return {err: 'no currentId'};
      const sr = await fetch('/api/tasks/stop/' + mid, {method:'POST', credentials:'include',
        headers: {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json'},
        body: JSON.stringify({reason: 'turn death — resident loop cure'})});
      const sb = await sr.text();
      const cr = await fetch('/api/chat/continue', {method:'POST', credentials:'include',
        headers: {'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json',
                  'X-FE-Version': 'prod-fe-1.1.98'},
        body: JSON.stringify({message_id: mid})});
      return {stop_http: sr.status, stop_body: sb.slice(0, 80), cont_http: cr.status};
    })()""" % CHAT
    try:
        r = _api_eval(js)
    except Exception as e:
        return f"stop-cure probe err: {str(e)[:100]}"
    closed = r.get("cont_http") == 410
    return f"stop_http={r.get('stop_http')} cont_http={r.get('cont_http')} — {'CLOSED' if closed else 'slot state unknown'}"


def send_nudge():
    tf = "/tmp/ppr022_composer_nudge.txt"
    with open(tf, "w") as f:
        f.write(NUDGE)
    try:
        p = subprocess.run([PY, os.path.join(BASE, "dispatch_worker.py"),
                            "send", SESSION, "@" + tf],
                           capture_output=True, text=True, timeout=280)
        out = (p.stdout or "").strip().splitlines()
        return out[-1] if out else "no-output"
    except subprocess.TimeoutExpired:
        return "shell-timeout (send may still have landed)"


def batch_rows():
    """All assistant batch sizes via the home tab (never the wedged chat tab)."""
    import channel
    home = next(t for t in channel.list_tabs()
                if (t.get("url") or "").rstrip("/") == "https://chat.z.ai")
    ws = channel.CDP(home["webSocketDebuggerUrl"])
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
          const hdr = {Authorization: 'Bearer ' + tok};
          const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store', headers: hdr});
          const j = await r.json();
          const msgs = ((j.chat||{}).history||{}).messages || {};
          const ids = Object.values(msgs).map(m=>m.id).filter(Boolean);
          const br = await fetch('/api/v1/chats/%s/messages/batch', {
            credentials:'include', cache:'no-store', method:'POST',
            headers: Object.assign({'Content-Type':'application/json'}, hdr),
            body: JSON.stringify({ids})});
          const bj = await br.json();
          const data = (bj && (bj.data || bj.messages)) || {};
          const rows = [];
          for (const [id, m] of Object.entries(data)) {
            if (!m || (m.role||'assistant')==='user') continue;
            const blocks = m.content_blocks || m.blocks || [];
            rows.push({id: id.slice(0,8), n: blocks.length,
                       txt: JSON.stringify(blocks.slice(-3)).slice(0,500)});
          }
          return JSON.stringify(rows);
        })()""" % (CHAT, CHAT)
        raw = ws.eval(js, await_promise=True, timeout=90)
        return json.loads(raw)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _totals():
    rows = batch_rows()
    return sum(r.get("n", 0) for r in rows)


def _live_check(window_s=110):
    """True if assistant blocks are growing (a live turn is producing)."""
    try:
        a = _totals()
        time.sleep(window_s)
        b = _totals()
        return b > a, a, b
    except Exception:
        return False, -1, -1


def _watch(cycle, max_s=TURN_WATCH_S):
    """Watch the turn; returns True on report-seen, False on static/timeout."""
    static, last_sig, t0 = 0, None, time.time()
    while time.time() - t0 < max_s:
        time.sleep(TURN_POLL_S)
        try:
            rows = batch_rows()
        except Exception as e:
            log(f"probe err: {e}")
            static += 1  # a dead probe surface counts toward refire
            if static >= STATIC_REFIRE:
                log("probe surface dead + turn static — next cycle (fresh tabs)")
                return False
            continue
        joined = " ".join(r.get("txt", "") for r in rows)
        if REPORT_MARK in joined:
            log("REPORT MARKER SEEN")
            state({"cycle": cycle, "phase": "REPORT-SEEN"})
            outbox("PPR-023: COMPLETION REPORT marker detected — Lead review starting.")
            open(os.path.join(FLAGS, "ppr023_report_seen.flag"), "w").write(str(int(time.time())))
            return True
        sig = tuple(sorted((r["id"], r["n"]) for r in rows))
        if sig == last_sig:
            static += 1
        else:
            static = 0
            last_sig = sig
        if static >= STATIC_REFIRE:
            log(f"turn static ({len(rows)} batches) — next cycle")
            return False
    log("turn still producing at cap — next cycle anyway (checkpoint law protects)")
    return False


def main():
    log(f"composer loop armed: {SESSION} @ {CHAT[:8]}")
    outbox("PPR-023 composer loop (stop-cure edition) armed: §8 cure + painter-waited composer nudges until the completion report.")
    for cycle in range(1, MAX_CYCLES + 1):
        # LIVE-CHECK first: never stop-cure a producing turn
        state({"cycle": cycle, "phase": "live-check"})
        live, a, b = _live_check()
        if live:
            log(f"cycle {cycle}: live turn producing ({a}->{b} blocks) — watching")
            state({"cycle": cycle, "phase": "watching-live"})
            if _watch(cycle):
                return 0
            continue
        state({"cycle": cycle, "phase": "tab-hunt"})
        kept = close_chat_tabs()
        if kept:
            tab = kept
            log(f"cycle {cycle}: REUSING responsive tab {tab['id'][:8]}")
        else:
            tab = fresh_tab()
            log(f"cycle {cycle}: fresh tab {tab['id'][:8]} — waiting for paint")
            if not wait_paint(tab["id"]):
                log("paint timeout — retrying cycle with a new tab")
                continue
        # registry pointer fix (§3.8): dispatch_worker.send resolves the
        # session's tab from the registry — a stale pointer makes every send
        # report "session tab LOST" even though a live tab exists.
        try:
            import dispatch_worker as dw
            dw._save({"action": "tab-reopen", "name": SESSION, "tab_id": tab["id"],
                      "url": URL, "ts": int(time.time()),
                      "note": "composer loop: keep the send path on this tab"})
        except Exception as e:
            log(f"registry pointer fix failed: {str(e)[:80]}")
        state({"cycle": cycle, "phase": "stop-cure"})
        sc = stop_cure()
        log(f"cycle {cycle}: stop-cure -> {sc}")
        state({"cycle": cycle, "phase": "sending"})
        res = send_nudge()
        log(f"cycle {cycle}: send -> {res[:160]}")
        state({"cycle": cycle, "phase": "watching", "last_send": res[:200]})
        if _watch(cycle):
            return 0
    log("cycle cap — Lead attention")
    state({"phase": "CYCLE-CAP"})
    outbox("PPR-023 composer loop hit the cycle cap — Lead attention.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
