#!/usr/bin/env python3
"""wave_watch.py — gentle-mode capacity-gate watcher for the current worker
wave (Task-73 doctrine: single-send probes on a fixed cadence so the capacity
window opens onto ONE clean send; server-side tree is the truth).

Lanes + chat ids resolve from flags/session_registry.jsonl. A lane is
GENERATING when its server-side tree holds >=1 assistant message. Each cycle
probes at most ONE non-generating lane with a begin-directive
(dispatch_worker.py send). Everything logs to logs/wave-watch.log.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "logs", "wave-watch.log")
REG = os.path.join(BASE, "flags", "session_registry.jsonl")
PROBE_EVERY = 300  # gentle cadence (s)
MAX_HOURS = 20

BEGIN_MSG = ("Begin now. Execute the full task packet above exactly as "
             "specified, and deliver per its mandated report format.")



def page_eval(js, timeout=45):
    tab = channel.find_tab("chat.z.ai")
    if tab is None:
        raise RuntimeError("no chat.z.ai tab open")
    ws = channel.CDP(tab["webSocketDebuggerUrl"])
    try:
        return ws.eval(js, await_promise=True, timeout=timeout)
    finally:
        ws.close()

def log(msg):
    line = f"[{time.strftime('%H:%M:%S', time.gmtime())}Z] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def lanes():
    out = {}
    try:
        for line in open(REG):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event") == "void":
                out.pop(r.get("name"), None)
                continue
            name = r.get("name")
            url = r.get("url") or ""
            if name and "/c/" in url:
                out[name] = url.split("/c/")[-1]
    except FileNotFoundError:
        pass
    return out


def tree_stats(cid):
    """Return (total_msgs, assistant_msgs, newest_role) via the in-page API."""
    js = f"""
    (async () => {{
      const t = localStorage.getItem('token') || '';
      const r = await fetch('/api/v1/chats/{cid}', {{credentials:'include',
        headers: {{'Authorization': 'Bearer ' + t}}}});
      const t2 = await r.text();
      return t2.slice(0, 400000);
    }})()
    """
    raw = page_eval(js, timeout=60)
    d = json.loads(raw)
    hist = (d.get("chat") or {}).get("history") or {}
    mmap = hist.get("messages") or {}
    msgs = list(mmap.values())
    assistant = [m for m in msgs if m.get("role") == "assistant"]
    newest = msgs[-1].get("role") if msgs else None
    return len(msgs), len(assistant), newest


def main():
    log("wave watcher started (gentle-mode, 300s cadence)")
    generating = {}
    rr = []
    start = time.time()
    while time.time() - start < MAX_HOURS * 3600:
        try:
            ls = lanes()
        except Exception as e:
            log(f"registry read error: {e}")
            time.sleep(60)
            continue
        if not ls:
            log("no lanes in registry — waiting")
            time.sleep(120)
            continue
        # refresh round-robin list with lanes not yet generating
        for name in ls:
            if name not in rr and name not in generating:
                rr.append(name)
        for name in list(generating):
            if name not in ls:
                del generating[name]
        pending = [n for n in rr if n not in generating]
        if not pending:
            alive = sum(1 for n in generating if n in ls)
            log(f"all {alive} lanes generating — watcher exiting")
            return 0
        # server-side check of every pending lane (cheap, one tab)
        still = []
        for name in pending:
            cid = ls[name]
            try:
                total, assist, newest = tree_stats(cid)
            except Exception as e:
                log(f"{name}: tree check error {e}")
                still.append(name)
                continue
            if assist > 0:
                generating[name] = cid
                log(f"{name}: GENERATING (assistant msgs={assist}, total={total})")
            else:
                still.append((name, total))
        pending = [n for n in pending if n not in generating]
        if pending:
            # probe ONE lane this cycle (round-robin)
            name = pending[0]
            rr.remove(name)
            rr.append(name)
            log(f"probing {name} with begin-directive (pending={len(pending)})")
            try:
                p = subprocess.run(
                    [sys.executable, os.path.join(BASE, "dispatch_worker.py"),
                     "send", name, BEGIN_MSG],
                    capture_output=True, text=True, timeout=420, cwd=BASE)
                tail = (p.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
                log(f"{name}: probe -> {tail[0][:160]}")
            except subprocess.TimeoutExpired:
                log(f"{name}: probe timed out (assault running) — tolerated")
        time.sleep(PROBE_EVERY)
    log("watcher max-hours reached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
