#!/usr/bin/env python3
"""wave3_rekick_012.py — rekick prod-012 when prod-011's slot frees.

2026-10-02 18:05 (lead): the first signed kick for 012 hit
MODEL_CONCURRENCY_LIMIT (one generation slot per account; 011's worker
holds it for its whole end-to-end turn). This watcher polls 011's turn
state every 60s; when the turn completes (report marker, done flag, or
content stable for 3 polls + not busy in DOM), it fires the signed kick
for 012 once and exits. Also exits if 012 starts generating on its own
(platform spawn-wall lift).
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

C011 = "7c67ccc2-b20d-4183-94a1-df04fce73a11"
C012 = "0686224a-1ed9-4716-afb3-567c251d8359"
MARKER = "COMPLETION REPORT"


def outbox(text):
    with open(os.path.join(BASE, "flags", "agent_outbox.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.time(), "from": "agent", "text": text}) + "\n")


def _tree(ws, cid):
    """(n_msgs, last_assistant_content_len, has_report, has_done_flag)."""
    js = """
    (async () => {
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/chats/%s', {credentials:'include',
        headers: {'Authorization': 'Bearer ' + t}});
      const d = await r.json();
      const msgs = (d.chat && d.chat.history && d.chat.history.messages) || {};
      let assistant = null;
      for (const m of Object.values(msgs)) {
        if (m.role === 'assistant') assistant = m;   // last wins
      }
      const content = assistant ? JSON.stringify(assistant.content || '') : '';
      return JSON.stringify({
        n: Object.keys(msgs).length,
        hasAssistant: !!assistant,
        len: content.length,
        report: content.includes('%s'),
        done: !!(assistant && assistant.done)
      });
    })()
    """ % (cid, MARKER)
    raw = ws.eval(js, await_promise=True, timeout=60)
    return json.loads(raw)


def _busy(tab_id_prefix):
    """Stop/Pause button presence in a worker tab (True = generating)."""
    for t in channel.list_tabs():
        if t["id"].startswith(tab_id_prefix):
            try:
                ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                try:
                    v = ws.eval(
                        "(() => { const btns = Array.from(document.querySelectorAll('button'))"
                        ".map(b => (b.innerText||'').trim());"
                        " return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 1 : 0; })()",
                        timeout=15)
                    return v == 1
                finally:
                    ws.close()
            except Exception:
                return False
    return None  # tab gone


def main():
    mirror = channel.find_tab("chat.z.ai")
    if mirror is None:
        print("no mirror tab", file=sys.stderr)
        return 1
    stable = 0
    last_len = -1
    while True:
        try:
            ws = channel.CDP(mirror["webSocketDebuggerUrl"], timeout=30)
            try:
                t12 = _tree(ws, C012)
            finally:
                ws.close()
        except Exception as e:  # noqa: BLE001
            print("tree poll error:", e, file=sys.stderr)
            time.sleep(60)
            continue

        if t12.get("hasAssistant") and t12.get("len", 0) > 200:
            outbox("wave3 rekick: 012 is generating on its own (len=%d) — no kick needed"
                   % t12["len"])
            print("012 generating already; exiting")
            return 0

        try:
            ws = channel.CDP(mirror["webSocketDebuggerUrl"], timeout=30)
            try:
                t11 = _tree(ws, C011)
            finally:
                ws.close()
        except Exception as e:  # noqa: BLE001
            print("tree poll error:", e, file=sys.stderr)
            time.sleep(60)
            continue

        busy = _busy("E4323D85")  # 011 worker tab
        print("[%s] 011: len=%d report=%s done=%s busy=%s | 012: len=%d"
              % (time.strftime("%H:%M:%S"), t11.get("len", 0), t11.get("report"),
                 t11.get("done"), busy, t12.get("len", 0)), flush=True)

        finished = t11.get("report") or t11.get("done")
        if not finished:
            if t11.get("len", 0) == last_len and t11.get("len", 0) > 500 and busy is False:
                stable += 1
            else:
                stable = 0
            last_len = t11.get("len", 0)
            if stable >= 3:
                finished = True  # 3 min stable + idle DOM = turn over

        if finished:
            outbox("wave3 rekick: 011 turn finished (len=%d report=%s) — firing 012 kick"
                   % (t11.get("len", 0), t11.get("report")))
            time.sleep(30)  # let the slot actually free server-side
            log = os.path.join(BASE, "logs", "kick-012-retry.log")
            subprocess.call([
                "python3", os.path.join(BASE, "dfork_launch.py"), log,
                "python3", os.path.join(BASE, "kick_queued.py"), C012])
            print("012 kick fired (log: logs/kick-012-retry.log); exiting")
            return 0

        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
