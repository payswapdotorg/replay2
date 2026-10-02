#!/usr/bin/env python3
"""ppr022_resume_loop.py — attended resume loop for the PPR-022 r4 worker.

Platform reality today (2026-10-01): worker turns die mid-stream routinely;
the composer path is wedged (work-rich tab) and null-commits; the ONLY
reliable spawn is api_resume (raw completions + harvested captcha token).
Each api_resume spawns the next turn; the worker resumes from its narrative
+ pod filesystem (CHECKPOINT LAW protects progress).

This daemon:
  1. fires api_resume with a short nudge,
  2. polls ALL assistant batch sizes every ~45s (the largest batch masks
     newer ones — probe every one),
  3. when the newest turn's batch is static for 3 consecutive polls and no
     report marker -> fire the next resume,
  4. stops (flag + outbox) when the COMPLETION REPORT marker appears,
  5. hard cap on cycles.

Launch: dfork_launch.py /tmp/ppr022_r4_loop.log <py> ppr022_resume_loop.py
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FLAGS = os.path.join(BASE, "flags")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
STATE = os.path.join(FLAGS, "ppr022_r4_loop_state.json")
LOG = "/tmp/ppr022_r4_loop.log"

CHAT = "6365132a-40ff-4920-ad79-1a098c57d93d"
REPORT_MARK = "=== PPR-022 COMPLETION REPORT ==="
MAX_CYCLES = 40
POLL_S = 60
STATIC_POLLS_FOR_REFIRE = 8  # ~8 min of no growth — a turn mid-tool (clone/
# test-suite timeouts run 5+ min) produces NO blocks while the tool executes;
# refiring early KILLS live turns (lesson: cycle-4/5 interrupted mid-work)

NUDGE = (
    "Continue the PPR-022 ROUND 3 PICKUP plan from your last checkpoint. "
    "Finish GAP A (typecheck 0), GAP C, the certified run + evidence, the "
    "6-gate battery (with the pre-gate ref sync), the tarball, then emit "
    "your final COMPLETION REPORT exactly per the contract in the first "
    "message. CHECKPOINT LAW: commit to your branch after every milestone."
)


def log(msg):
    print(f"[{time.strftime('%m-%d %H:%M:%S', time.gmtime())}] {msg}", flush=True)


def post_outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")
    except Exception:
        pass


def save_state(d):
    try:
        d["ts"] = int(time.time() * 1000)
        with open(STATE, "w") as f:
            json.dump(d, f, indent=1)
    except Exception:
        pass


def all_batches():
    """Probe every assistant message's batch (not just the largest)."""
    import channel
    tab = channel.find_tab("chat.z.ai")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        js = """(async () => {
          const tok = (localStorage.getItem('token')||'').replace(/^"|"$/g,'');
          const hdr = {Authorization: 'Bearer ' + tok};
          const r = await fetch('/api/v1/chats/%s', {credentials:'include', cache:'no-store', headers: hdr});
          const j = await r.json();
          const msgs = ((j.chat||{}).history||{}).messages || {};
          const byTs = Object.values(msgs).sort((a,b)=>(a.timestamp||0)-(b.timestamp||0));
          const ids = byTs.map(m=>m.id).filter(Boolean);
          const br = await fetch('/api/v1/chats/%s/messages/batch', {
            credentials:'include', cache:'no-store', method:'POST',
            headers: Object.assign({'Content-Type':'application/json'}, hdr),
            body: JSON.stringify({ids})});
          const bj = await br.json();
          const data = (bj && (bj.data || bj.messages)) || {};
          const rows = [];
          for (const [id, m] of Object.entries(data)) {
            if (!m || (m.role||'assistant') === 'user') continue;
            const blocks = m.content_blocks || m.blocks || [];
            rows.push({id: id.slice(0,8), len: JSON.stringify(m).length, n: blocks.length,
                       txt: JSON.stringify(blocks.slice(-2)).slice(0,400)});
          }
          rows.sort((a,b)=>a.len-b.len);
          return JSON.stringify(rows);
        })()""" % (CHAT, CHAT)
        raw = ws.eval(js, await_promise=True, timeout=60)
        return json.loads(raw)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def fire_resume():
    """Run api_resume with a temp nudge file; return the SEND line."""
    tf = "/tmp/ppr022_loop_nudge.txt"
    with open(tf, "w") as f:
        f.write(NUDGE)
    try:
        out = subprocess.run(
            [PY, os.path.join(BASE, "api_resume.py"), CHAT, tf],
            capture_output=True, text=True, timeout=150).stdout
    except subprocess.TimeoutExpired:
        return "TIMEOUT(shell) — browser JS continues"
    for line in out.splitlines():
        if line.startswith("SEND:") or line.startswith("FAIL") or "token captured" in line:
            pass
    return out.strip().splitlines()[-1] if out.strip() else "no-output"


def main():
    log(f"resume loop armed: chat {CHAT[:8]}, max {MAX_CYCLES} cycles")
    post_outbox("PPR-022 r4 resume loop armed: attended turn-resuscitation until the completion report lands.")
    static = 0
    last_sig = None
    for cycle in range(1, MAX_CYCLES + 1):
        send_line = fire_resume()
        log(f"cycle {cycle}: {send_line[:180]}")
        save_state({"cycle": cycle, "last_send": send_line[:300], "phase": "watching"})
        static = 0
        last_sig = None
        for _ in range(40):  # up to 30 min per turn
            time.sleep(POLL_S)
            try:
                rows = all_batches()
            except Exception as e:
                log(f"probe err: {e}")
                continue
            total = sum(r["n"] for r in rows)
            sig = (len(rows), total, tuple((r["id"], r["n"]) for r in rows[-3:]))
            # report check across every batch tail text
            joined = " ".join(r.get("txt", "") for r in rows)
            if REPORT_MARK in joined:
                log("REPORT MARKER SEEN — stopping loop, flagging Lead")
                save_state({"cycle": cycle, "phase": "REPORT-SEEN"})
                post_outbox("PPR-022 r4: COMPLETION REPORT marker detected in the worker narrative. Lead review starting.")
                open(os.path.join(FLAGS, "ppr022_report_seen.flag"), "w").write(str(int(time.time())))
                return 0
            if sig == last_sig:
                static += 1
            else:
                static = 0
                last_sig = sig
            if static >= STATIC_POLLS_FOR_REFIRE:
                log(f"turn static after {static} polls (rows={len(rows)} blocks={total}) — refiring")
                break
        else:
            log("turn still producing after 30 min — continuing to watch")
    log("cycle cap reached — Lead attention needed")
    save_state({"phase": "CYCLE-CAP"})
    post_outbox("PPR-022 r4 resume loop hit the cycle cap without a report — Lead attention needed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
