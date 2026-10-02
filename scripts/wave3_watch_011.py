#!/usr/bin/env python3
"""wave3_watch_011.py — monitor the live 011 worker turn; dispatch 012 on completion.

The 011 turn (chat a4931361, tab 71947179) is SPA-owned: the tab holds the
stream and persists the transcript. This watcher NEVER touches that tab —
read-only CDP checks + chats-API polls via the mirror tab. When the final
report marker (COMPLETION REPORT) appears in the assistant content (or the
turn completes), it fires the 012 create (proven flow: debounce-ladder
real-click send) and exits.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

CID = "a4931361-deb4-4300-afcd-a42b74e52ba3"
MARKER = "COMPLETION REPORT"
REG = os.path.join(BASE, "flags", "session_registry.jsonl")
OUTBOX = os.path.join(BASE, "flags", "agent_outbox.jsonl")


def outbox(text):
    with open(OUTBOX, "a") as f:
        f.write(json.dumps({"ts": time.time(), "from": "agent", "text": text}) + "\n")


def tree_state():
    """{n, alen, has_report, done} via the mirror tab (read-only)."""
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        return None
    ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = ws.eval("""
        (async () => {
          const t = localStorage.getItem('token') || '';
          const r = await fetch('/api/v1/chats/%s?cb=' + Date.now(), {credentials:'include',
            headers: {'Authorization': 'Bearer ' + t}, cache: 'no-store'});
          const d = await r.json();
          const msgs = (d.chat && d.chat.history && d.chat.history.messages) || {};
          let n = 0, alen = 0, report = false, done = false;
          for (const m of Object.values(msgs)) {
            n += 1;
            if (m.role === 'assistant') {
              const c = JSON.stringify(m.content || '');
              alen = c.length;
              report = c.includes('%s');
              done = !!m.done;
            }
          }
          return JSON.stringify({n: n, alen: alen, report: report, done: done,
                                 upd: d.updated_at});
        })()
        """ % (CID, MARKER), await_promise=True, timeout=60)
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        print("tree poll err:", str(e)[:60], flush=True)
        return None
    finally:
        ws.close()


def worker_tab_alive():
    for t in channel.list_tabs():
        if CID in (t.get("url") or ""):
            return t["id"]
    return None


def main():
    outbox("011 WORKER TURN IS LIVE (chat a4931361, SPA-owned tab holds the stream): the worker is "
           "executing CAMSCAN-PROD-011 end-to-end (thinking phase started; workspace ws-a2893d1d "
           "provisioned). Expected runtime 30-90 min. On completion, PROD-012 auto-dispatches.")
    last_alen = -1
    stable = 0
    t0 = time.time()
    while True:
        st = tree_state()
        if st:
            age_min = int((time.time() - t0) / 60)
            print("[%dm] n=%s alen=%s report=%s done=%s tab=%s"
                  % (age_min, st.get("n"), st.get("alen"), st.get("report"),
                     st.get("done"), (worker_tab_alive() or "GONE")[:8]), flush=True)

            if st.get("report"):
                outbox("011 FINAL REPORT DETECTED (len=%d) — harvesting phase next; dispatching 012 now"
                       % st.get("alen", 0))
                break
            if st.get("done") and st.get("alen", 0) > 200:
                outbox("011 turn DONE (len=%d, no report marker — inspect on harvest)"
                       % st.get("alen", 0))
                break
            # stalled? content static 10 min AND worker tab gone
            if st.get("alen", 0) == last_alen:
                stable += 1
            else:
                stable = 0
            last_alen = st.get("alen", 0)
            if stable >= 10 and worker_tab_alive() is None:
                outbox("011 STALL: content static 10 min and worker tab gone (alen=%d) — lead attention"
                       % st.get("alen", 0))
                print("stalled — exiting for lead inspection", flush=True)
                return 1
        time.sleep(60)

    # completion: wait for the slot to settle, then dispatch 012
    print("011 complete — waiting 60s for slot settle, then dispatching 012...", flush=True)
    time.sleep(60)
    log = os.path.join(BASE, "logs", "dispatch-camscan-prod-012.log")
    subprocess.call(["python3", os.path.join(BASE, "dfork_launch.py"), log,
                     "python3", os.path.join(BASE, "dispatch_worker.py"),
                     "create", "camscan-prod-012",
                     os.path.join(BASE, "worker-prompts", "camscan-prod-012.md")])
    outbox("012 dispatched (create flow, debounce-ladder send) after 011 completion — "
           "monitoring continues")
    print("012 dispatch fired", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
