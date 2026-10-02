#!/usr/bin/env python3
"""lead_watch_dual.py — resident dual-chat watch for the PPR-020 wave.

Watches BOTH live worker chats (the promoted orphan + the nudge-queued
main), polling server-side truth every 45s:
  - msgs / updated / batch-chars per chat
  - END REPORT detection with the filled-regex discriminator (40-hex sha,
    no placeholder tokens in the 450-char window after the headline)
  - transition logging (queue-drain, stream-resume, stream-death, report)
  - Page.reload self-heal when the tab network wedges (max once / 5 min)
  - heartbeat file + outbox notices on transitions

NO auto-assault: both chats own live/queued assets; re-dispatch is the
Lead's call on wakeup. Logs to stdout (dfork'd into /tmp/lead_dual.log).
"""
import json
import os
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel

CHATS = {
    "orphan": {
        "uuid": "1d70b4fb-fd07-43b0-b85a-0bc4a07fa92f",
        "role": "primary PPR-020 worker (promoted 09:52)",
    },
    "main": {
        "uuid": "33b13b62-dc80-42ac-b381-b12e56b1275b",
        "role": "secondary (turn-1 persisted 1.28MB; nudge queued since 07:19; ws expired)",
    },
}
MARKER = "PPR-020 COMPLETION REPORT"
HEARTBEAT = "/home/z/replay2/scripts/flags/lead_dual.heartbeat"
OUTBOX = "/home/z/replay2/scripts/flags/agent_outbox.jsonl"
POLL = 45
STALE_STREAM_MIN = 40  # stream-death verdict threshold (the ~35-40 min pattern)


def log(msg):
    print(f"[dual] {time.strftime('%H:%M:%S')} {msg}", flush=True)


def outbox(kind, text):
    try:
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "text": text}
        os.makedirs(os.path.dirname(OUTBOX), exist_ok=True)
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log(f"outbox-write-fail {e}")


def beat(state):
    try:
        os.makedirs(os.path.dirname(HEARTBEAT), exist_ok=True)
        with open(HEARTBEAT, "w") as f:
            json.dump({"pid": os.getpid(), "ts": time.time(), "state": state}, f)
    except Exception:
        pass


def ensure_tab():
    """A tab on the orphan chat (primary viewing surface).

    2026-09-29 doctrine: a reload that hits the flaky-VPN window lands on
    chrome-error://chromewebdata/ (origin null -> localStorage throws
    SecurityError). Detect the error page / wrong document and RE-NAVIGATE
    instead of trusting the target-list URL (which lags)."""
    want = f"https://chat.z.ai/c/{CHATS['orphan']['uuid']}"
    tab = None
    for t in channel.list_tabs():
        if CHATS["orphan"]["uuid"][:8] in (t.get("url") or ""):
            tab = t
            break
    if tab is None:
        tab = channel.new_tab(want)
        time.sleep(9)
        return tab
    try:
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            href = ws.eval("location.href", timeout=12) or ""
        finally:
            ws.close()
        if "chat.z.ai" in href and CHATS["orphan"]["uuid"][:8] in href:
            return tab
    except Exception:
        pass
    # error page / wedged document: navigate fresh
    try:
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=25)
        try:
            ws.call("Page.enable", {})
            ws.call("Page.navigate", {"url": want})
        finally:
            ws.close()
        time.sleep(9)
    except Exception:
        pass
    return tab


PROBE_JS_TMPL = """(async () => {
  const tok = (localStorage.getItem('token') || '').replace(/^"|"$/g, '');
  const hdr = tok ? {Authorization: 'Bearer ' + tok} : {};
  const out = {};
  for (const cid of %s) {
    try {
      const r = await fetch('/api/v1/chats/' + cid, {credentials: 'include', cache: 'no-store', headers: hdr});
      if (!r.ok) { out[cid.slice(0,8)] = {err: 'http-' + r.status}; continue; }
      const j = await r.json();
      const msgs = ((j.chat || {}).history || {}).messages || {};
      const byTs = Object.values(msgs).sort((a,b) => (a.timestamp||0)-(b.timestamp||0));
      let reportInAssistant = false;
      for (const m of byTs) {
        if (m.role !== 'assistant') continue;
        const c = Array.isArray(m.content) ? m.content : (m.content || '');
        if (JSON.stringify(c).indexOf(%s) >= 0) reportInAssistant = true;
      }
      const ids = byTs.map(m => m.id).filter(Boolean);
      let batchChars = -1;
      try {
        if (ids.length) {
          const br = await fetch('/api/v1/chats/' + cid + '/messages/batch', {
            credentials: 'include', cache: 'no-store', method: 'POST',
            headers: Object.assign({'Content-Type': 'application/json'}, hdr),
            body: JSON.stringify({ids})});
          if (br.ok) {
            const bj = await br.json();
            const data = (bj && (bj.data || bj.messages)) || {};
            batchChars = 0;
            for (const id of Object.keys(data)) {
              const m = data[id];
              if (!m || (m.role || 'assistant') === 'user') continue;
              const whole = JSON.stringify(m);
              batchChars += whole.length;
              let mi = -1;
              while ((mi = whole.indexOf(%s, mi + 1)) >= 0) {
                const win = whole.slice(mi, mi + 450);
                const hasHex = /\\b[0-9a-f]{40}\\b/.test(win);
                const hasPlaceholder = /<[a-zA-Z][^>]{2,60}>/.test(win);
                if (hasHex && !hasPlaceholder) reportInAssistant = true;
              }
            }
          }
        }
      } catch (e) {}
      out[cid.slice(0,8)] = {msgs: byTs.length, updated: j.updated_at || j.updated || 0,
                             batchChars: batchChars, report: reportInAssistant};
    } catch (e) { out[cid.slice(0,8)] = {err: String(e).slice(0, 50)}; }
  }
  out._now = Math.floor(Date.now() / 1000);
  return JSON.stringify(out);
})()"""


def probe(ws):
    import json as _json
    js = PROBE_JS_TMPL % (
        _json.dumps([c["uuid"] for c in CHATS.values()]),
        _json.dumps(MARKER), _json.dumps(MARKER))
    raw = ws.eval(js, await_promise=True, timeout=60)
    return _json.loads(raw)


def main():
    log("watch start: " + ", ".join(f"{k}={v['uuid'][:8]}" for k, v in CHATS.items()))
    outbox("watch-start", "lead_watch_dual armed on 1d70b4fb (primary, generating) + 33b13b62 (queued)")
    prev = {}
    last_reload = 0
    err_streak = 0
    last_adv = {}
    while True:
        state = {"ts": time.time()}
        try:
            tab = ensure_tab()
            ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=45)
            try:
                d = probe(ws)
            finally:
                ws.close()
            err_streak = 0
            now = d.get("_now", 0)
            for key, cfg in CHATS.items():
                u8 = cfg["uuid"][:8]
                cur = d.get(u8) or {}
                if "err" in cur:
                    log(f"{key} probe-err {cur['err']}")
                    continue
                p = prev.get(key) or {}
                # transition: report
                if cur.get("report") and not p.get("report"):
                    log(f"{key} *** END REPORT DETECTED (msgs={cur.get('msgs')}) ***")
                    outbox("harvest-ready", f"{key} {cfg['uuid']}: PPR-020 COMPLETION REPORT detected — harvest path")
                # transition: msgs advanced
                if cur.get("msgs", 0) > p.get("msgs", 0) and p:
                    log(f"{key} msgs {p.get('msgs')}->{cur.get('msgs')} (turn accepted/finalized)")
                    outbox("turn-transition", f"{key}: msgs {p.get('msgs')}->{cur.get('msgs')}")
                # stream liveness
                bc = cur.get("batchChars", -1)
                if bc > (p.get("batchChars") or -1):
                    last_adv[key] = time.time()
                    if p and (p.get("batchChars") or -1) > 0:
                        log(f"{key} batch advancing {p.get('batchChars')}->{bc}")
                if bc >= 0 and key in last_adv:
                    quiet_min = (time.time() - last_adv[key]) / 60
                    if quiet_min > STALE_STREAM_MIN:
                        # only flag once per hour of quiet
                        if not p.get("flagged_stale"):
                            log(f"{key} stream quiet {quiet_min:.0f}min (updated={cur.get('updated')}) — possible stream death")
                            outbox("stream-quiet", f"{key}: batch static {quiet_min:.0f}min — Lead differential advised (nudge doctrine)")
                            prev[key] = dict(cur, flagged_stale=True)
                            continue
                state[key] = {"msgs": cur.get("msgs"), "updated": cur.get("updated"),
                              "batchChars": bc, "report": cur.get("report")}
                if not cur.get("report"):
                    prev[key] = cur
            beat(state)
        except Exception as e:
            err_streak += 1
            log(f"cycle-err #{err_streak}: {str(e)[:90]}")
            if err_streak >= 2 and time.time() - last_reload > 300:
                try:
                    # navigate (not reload): reload can strand the tab on
                    # chrome-error://chromewebdata/ when the VPN flaps
                    want = f"https://chat.z.ai/c/{CHATS['orphan']['uuid']}"
                    tab = ensure_tab()
                    ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
                    try:
                        ws.call("Page.enable", {})
                        ws.call("Page.navigate", {"url": want})
                    finally:
                        ws.close()
                    last_reload = time.time()
                    log("tab network self-heal: Page.navigate")
                    time.sleep(8)
                except Exception as e2:
                    log(f"self-heal-fail {str(e2)[:60]}")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
