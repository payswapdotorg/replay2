#!/usr/bin/env python3
"""dep_watch.py — light completion watcher for the DEP Wave A chats.

Polls the server-side chat trees (committed assistant content) every CYCLE_S;
writes flags/<key>-complete.marker when a chat's committed assistant turn
contains 'COMPLETION REPORT' (the delivery contract's report block) or exceeds
DONE_CHARS. Logs one status line per chat per cycle to logs/dep_watch.log.

Memory-light by design (the OOM killer reaped a sentinel on 2026-09-15):
reuses an existing chat tab for the in-page fetch, falls back to a fresh tab,
closes every CDP socket, no rendering, no screenshots.

Exits 0 when all watched chats have markers; 4 after MAX_CYCLES.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel
import dep_chats

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "dep_watch.log")
CYCLE_S = 150
MAX_CYCLES = 240
DONE_CHARS = 5000

# 2026-09-16 (TL): chat ids are resolved DYNAMICALLY from the session
# registry (dep_chats.resolve) — re-landing rounds no longer need manual
# re-pointing. FALLBACK ids inside dep_chats keep the watch list non-empty.
CHATS = dep_chats.resolve()


def log(*args):
    line = time.strftime("[%H:%M:%S]") + " " + " ".join(str(a) for a in args)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def eval_js(js, timeout=50):
    """Prefer an existing chat tab (cheap); fall back to a fresh tab (wedge-proof)."""
    for t in channel.list_tabs():
        u = t.get("url") or ""
        if t.get("type") == "page" and "chat.z.ai/c/" in u:
            try:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
                try:
                    return c.eval(js, await_promise=True, timeout=timeout)
                finally:
                    c.close()
            except Exception:
                break
    t = channel.new_tab("https://chat.z.ai/")
    try:
        c = channel.CDP(t["webSocketDebuggerUrl"], timeout=25)
        for _ in range(15):
            try:
                if c.eval("document.readyState", await_promise=False, timeout=8) in ("interactive", "complete"):
                    break
            except Exception:
                pass
            time.sleep(1.5)
        return c.eval(js, await_promise=True, timeout=timeout)
    finally:
        try:
            channel.CDP(t["webSocketDebuggerUrl"], timeout=10).call(
                "Target.closeTarget", {"targetId": t.get("id")}, timeout=8)
        except Exception:
            pass


JS = """(async () => {
  const out = {};
  for (const [k, cid] of Object.entries(%s)) {
    try {
      const r = await fetch('/api/v1/chats/' + cid, {credentials: 'include'});
      if (r.status !== 200) { out[k] = {s: r.status}; continue; }
      const j = await r.json(); const d = j.data || j;
      const msgs = Object.values((d.chat && d.chat.history && d.chat.history.messages) || {});
      let aChars = 0, report = false;
      for (const m of msgs) {
        if (m.role !== 'assistant') continue;
        const c = typeof m.content === 'string' ? m.content : JSON.stringify(m.content || '');
        aChars += c.length;
        if (c.includes('COMPLETION REPORT')) report = true;
      }
      out[k] = {a: aChars, r: report, u: d.updated_at};
    } catch (e) { out[k] = {e: String(e).slice(0, 50)}; }
  }
  return JSON.stringify(out);
})()"""


def main():
    done = set()
    for n in CHATS:
        if os.path.exists(os.path.join(FLAGS, f"{n}-complete.marker")):
            done.add(n)
    log("watcher up; already-done:", sorted(done) or "none")
    for cycle in range(1, MAX_CYCLES + 1):
        if len(done) == len(CHATS):
            log("all chats complete — exiting")
            return 0
        try:
            # re-resolve every cycle: a fresh landing (new create row, no
            # void after it) switches this name onto the new chat id within
            # one cycle. Log the switch loudly.
            fresh = dep_chats.resolve()
            for n, cid in fresh.items():
                if CHATS.get(n) != cid:
                    log(f"RE-POINT {n}: {CHATS.get(n)} -> {cid} (registry live row)")
            CHATS.clear()
            CHATS.update(fresh)
            raw = eval_js(JS % json.dumps(CHATS))
            data = json.loads(raw) if isinstance(raw, str) else raw
            for k, v in data.items():
                if k in done:
                    continue
                if v.get("r") or (v.get("a") or 0) >= DONE_CHARS:
                    with open(os.path.join(FLAGS, f"{k}-complete.marker"), "w") as f:
                        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + json.dumps(v))
                    done.add(k)
                    log(f"COMPLETE {k}: {json.dumps(v)}")
                else:
                    log(f"cycle {cycle} {k}: {json.dumps(v)}")
        except Exception as e:
            log(f"cycle {cycle} probe ERR: {type(e).__name__} {str(e)[:80]}")
        try:
            with open(os.path.join(FLAGS, "dep_watch_heartbeat"), "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        time.sleep(CYCLE_S)
    log("MAX_CYCLES reached — exiting")
    return 4


if __name__ == "__main__":
    sys.exit(main())
