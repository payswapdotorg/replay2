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
STATE = os.path.join(FLAGS, "ppr022_composer_state.json")
CDP = "http://127.0.0.1:9222"

CHAT = "6365132a-40ff-4920-ad79-1a098c57d93d"
URL = f"https://chat.z.ai/c/{CHAT}"
SESSION = "ppr022-r4"
REPORT_MARK = "=== PPR-022 COMPLETION REPORT ==="
MAX_CYCLES = 25
PAINT_TIMEOUT_S = 1500       # 25 min max wait for tab paint
PAINT_POLL_S = 30
TURN_WATCH_S = 1800          # 30 min max per turn
TURN_POLL_S = 60
STATIC_REFIRE = 8            # ~8 min no growth => turn dead

NUDGE = (
    "FINAL STRETCH. Continue from your last checkpoint: you were reconciling "
    "the demo-mirror index test (your new demo entry legitimately changed "
    "the index; the hardcoded-expectation update is in your boundary or a "
    "Lead merge note per the surface rules). Then finalize "
    "deploy/evidence/ppr-022.json (honest status), build the tarball "
    "(tar czf /home/z/my-project/PPR-022-files.tgz $(git diff --name-only "
    "0d2c9dc..HEAD) + sha256sum), append the worklog, and emit your FINAL "
    "message: === PPR-022 COMPLETION REPORT === ... === END REPORT === "
    "exactly per the contract. The battery already PASSED "
    "(AI_EXECUTION_COMPLETE, 5/5 rules) — only the report emission remains."
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


def main():
    log(f"composer loop armed: {SESSION} @ {CHAT[:8]}")
    outbox("PPR-022 r4 composer loop armed: painter-waited composer nudges until the completion report.")
    for cycle in range(1, MAX_CYCLES + 1):
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
        state({"cycle": cycle, "phase": "sending"})
        res = send_nudge()
        log(f"cycle {cycle}: send -> {res[:160]}")
        state({"cycle": cycle, "phase": "watching", "last_send": res[:200]})
        # watch the turn
        static, last_sig, t0 = 0, None, time.time()
        while time.time() - t0 < TURN_WATCH_S:
            time.sleep(TURN_POLL_S)
            try:
                rows = batch_rows()
            except Exception as e:
                log(f"probe err: {e}")
                continue
            joined = " ".join(r.get("txt", "") for r in rows)
            if REPORT_MARK in joined:
                log("REPORT MARKER SEEN")
                state({"cycle": cycle, "phase": "REPORT-SEEN"})
                outbox("PPR-022 r4: COMPLETION REPORT marker detected — Lead review starting.")
                open(os.path.join(FLAGS, "ppr022_report_seen.flag"), "w").write(str(int(time.time())))
                return 0
            sig = tuple(sorted((r["id"], r["n"]) for r in rows))
            if sig == last_sig:
                static += 1
            else:
                static = 0
                last_sig = sig
            if static >= STATIC_REFIRE:
                log(f"turn static ({len(rows)} batches) — next cycle")
                break
        else:
            log("turn still producing at 30 min — next cycle anyway (checkpoint law protects)")
    log("cycle cap — Lead attention")
    state({"phase": "CYCLE-CAP"})
    outbox("PPR-022 r4 composer loop hit the cycle cap — Lead attention.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
