#!/usr/bin/env python3
"""canary_nudge_experiment.py — v3: reload+nudge a hung canary with the
redispatcher safely paused.

Established facts (2026-10-09 09:0x-09:1xZ, truth law):
  - Fresh agent-tab sends fire fetches that fail at network level (status-0
    beacons), the turn hangs silently, and the SPA enters a dead state where
    further submits fire ZERO fetches (v1 nudge: stream empty, busy 0).
  - native_resubmit doctrine: that error state is cleared by Page.reload.

v3 protocol (race-free):
  1. Watch the redispatch log for a fresh "create-w3a rc=0" line.
  2. SIGSTOP the redispatcher — it is in its sleep(START_WAIT), the safest
     instant to freeze; the canary tab cannot be voided while frozen.
  3. Reload the canary tab (clear SPA error state), settle, patch fetch,
     clear->focus->insert w3-nudge, submit.
  4. Watch up to 240s for TURN LIVE (busy button / delta frames).
     - LIVE: redispatcher stays STOPPED; exit 0; the TL verifies markers
       render, then SIGCONTs the redispatcher so its own check_alive sees
       the live canary and dispatches w3b + w3c.
     - DEAD: SIGCONT the redispatcher (resumes its normal void+recreate
       cycle); record honestly; exit nonzero.
"""
import json
import os
import signal
import subprocess
import sys
import time

BASE = "/home/z/replay2/scripts"
sys.path.insert(0, BASE)
import channel  # noqa: E402

NUDGE = open(os.path.join(BASE, "worker-prompts", "w3-nudge.txt")).read()
LOG = os.path.join(BASE, "logs", "canary-nudge-experiment.log")
REDISPATCH_LOG = os.path.join(BASE, "logs", "w3-redispatch.log")
REDISPATCH_PID = 10322

WATCH_JS = """(() => {
  window.__stream = '';
  if (!window.__origFetch) {
    window.__origFetch = window.fetch;
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.includes('/api/v2/chat/completions')) {
        const r = await window.__origFetch(input, init);
        const ct = r.headers.get('content-type') || '';
        if (ct.includes('event-stream')) {
          const reader = r.body.getReader(); const dec = new TextDecoder();
          const t0 = Date.now();
          (async () => {
            while (Date.now() - t0 < 3600000) {
              const {done, value} = await reader.read().catch(() => ({done: true}));
              if (value) { const s = dec.decode(value); window.__stream = (window.__stream + s).slice(-3000); }
              if (done) break;
            }
          })();
        } else { window.__stream = 'nonSSE:' + (await r.text()).slice(0, 400); }
        return r;
      }
      return window.__origFetch(input, init);
    };
    return 'patched';
  }
  return 'already-patched';
})()"""

BUSY_JS = ("(() => { const btns = Array.from(document.querySelectorAll('button'))"
           ".map(b => (b.innerText||'').trim());"
           " return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 1 : 0; })()")

MARKER_JS = ("(() => { const b = document.body.innerText || '';"
             " const ms = ['Thought Process','Ran ','Wrote ','Terminal',"
             "'Todo Progress','Explored','Read File'].filter(m => b.includes(m));"
             " return ms.join(','); })()")


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def live_w3a():
    rec = None
    for line in open(os.path.join(BASE, "flags", "session_registry.jsonl")):
        if line.strip():
            r = json.loads(line)
            if r.get("name") == "w3a":
                if r.get("action") in ("void", "failed", "done"):
                    rec = None
                elif r.get("sent") and not r.get("action"):
                    rec = r
    return rec


def main():
    log("v3 armed — waiting for fresh create-w3a rc=0 ...")
    # 1. wait for a fresh create completion
    pos0 = os.path.getsize(REDISPATCH_LOG)
    deadline = time.time() + 600
    target = None
    while time.time() < deadline:
        with open(REDISPATCH_LOG) as f:
            f.seek(pos0)
            chunk = f.read()
        pos0 += len(chunk)
        if "create-w3a rc=0" in chunk:
            time.sleep(3)  # registry write settle
            target = live_w3a()
            if target:
                break
        time.sleep(2)
    if not target:
        log("no fresh canary in window — abort (nothing touched)")
        return 1
    chat = target["url"].split("/")[-1]
    log("canary %s tab %s — pausing redispatcher (SIGSTOP %d)" %
        (chat[:8], target["tab_id"][:8], REDISPATCH_PID))
    # 2. freeze the redispatcher inside its sleep(START_WAIT)
    os.kill(REDISPATCH_PID, signal.SIGSTOP)
    stopped = True
    try:
        tab = None
        for t in channel.list_tabs():
            if chat[:12] in (t.get("url") or ""):
                tab = t
                break
        if not tab:
            log("no open tab for canary — resuming redispatcher, abort")
            return 1
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
        try:
            # 3. reload to clear the SPA error state (native_resubmit doctrine).
            #    The reload swaps the renderer and RESETS the DevTools socket
            #    (2026-09-20 lesson) — so fire the reload on this connection,
            #    then RECONNECT on a fresh one for the nudge phase.
            log("reloading canary tab ...")
            try:
                ws.call("Page.reload", {}, timeout=30)
            except Exception as e:
                log("reload call err (renderer swap may still proceed): %s" % str(e)[:60])
        finally:
            try:
                ws.close()
            except Exception:
                pass
        time.sleep(10)
        # reconnect on the post-reload socket — POLL for renderer readiness
        # (v3.1: the renderer swap outlives a fixed settle; a single eval at
        # +22s died with WebSocketTimeoutException at exactly +32s)
        ws = None
        for attempt in range(7):
            tab = None
            for t in channel.list_tabs():
                if chat[:12] in (t.get("url") or ""):
                    tab = t
                    break
            if not tab:
                log("tab gone after reload — resuming redispatcher, abort")
                os.kill(REDISPATCH_PID, signal.SIGCONT)
                stopped = False
                return 1
            try:
                ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
                href = ws.eval("location.href || '??'", timeout=8)
                blen = ws.eval("(document.body.innerText || '').length", timeout=8)
                log("renderer ready (attempt %d): %s len=%s" % (attempt, str(href)[:60], blen))
                if blen and int(blen) > 2000:
                    break  # chat page fully rendered
                # page still bootstrapping — drop this connection, wait more
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None
                time.sleep(12)
            except Exception as e:
                log("renderer not ready (attempt %d): %s" % (attempt, str(e)[:50]))
                try:
                    ws.close()
                except Exception:
                    pass
                ws = None
                time.sleep(12)
        if ws is None:
            log("renderer never stabilized — resuming redispatcher, abort")
            os.kill(REDISPATCH_PID, signal.SIGCONT)
            stopped = False
            return 1
        try:
            try:
                ws.call("Page.bringToFront", {}, timeout=10)
            except Exception:
                pass
            busy0 = ws.eval(BUSY_JS, timeout=10)
            log("busy after reload: %s; body len: %s" %
                (busy0, ws.eval("(document.body.innerText || '').length", timeout=15)))
            log("watch patch: %s" % ws.eval(WATCH_JS, timeout=20))
            log("clear: %s" % ws.eval(channel.CLEAR_JS, timeout=15))
            time.sleep(0.5)
            ws.eval("(() => { const i = document.querySelector('#chat-input, textarea');"
                    " if (i) { i.focus(); return 'ok'; } return 'gone'; })()", timeout=15)
            time.sleep(0.3)
            ws.call("Input.insertText", {"text": NUDGE})
            time.sleep(2.5)
            vlen = ws.eval("(document.querySelector('textarea')||{value:''}).value.length", timeout=15)
            log("nudge inserted: %s/%d chars" % (vlen, len(NUDGE)))
            log("submit: %s" % ws.eval(channel.SUBMIT_JS, timeout=15))
            # 4. watch (no void race — redispatcher frozen)
            for i in range(48):
                time.sleep(5)
                try:
                    stream = ws.eval('(window.__stream || "").slice(-350)', timeout=10)
                    busy = ws.eval(BUSY_JS, timeout=10)
                    markers = ws.eval(MARKER_JS, timeout=10)
                except Exception as e:
                    log("t+%02d eval fail: %s" % (i, str(e)[:50]))
                    continue
                log("t+%02d busy:%s markers:[%s] | %s" %
                    (i, busy, (markers or "")[:40], (stream or "")[:150].replace("\n", " ")))
                if busy == 1 or (stream and "delta_content" in stream):
                    log(">>> NUDGE TURN IS LIVE — redispatcher stays FROZEN; "
                        "TL: verify markers then SIGCONT %d <<<" % REDISPATCH_PID)
                    return 0
                if stream and ("MODEL_CONCURRENCY" in stream or "FRONTEND_CAPTCHA" in stream):
                    log(">>> explicit rejection — resuming redispatcher, recording")
                    os.kill(REDISPATCH_PID, signal.SIGCONT)
                    stopped = False
                    return 2
            log("turn did not go live (240s, recorded honestly)")
            os.kill(REDISPATCH_PID, signal.SIGCONT)
            stopped = False
            return 3
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception as e:
        log("EXPERIMENT ERROR: %r" % (e,))
        return 4
    finally:
        if stopped:
            try:
                os.kill(REDISPATCH_PID, signal.SIGCONT)
                log("safety: redispatcher resumed on exit path")
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
