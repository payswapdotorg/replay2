#!/usr/bin/env python3
"""native_resubmit.py — re-drive a worker turn through the SPA composer.

2026-10-02 doctrine (lead, hard-won):
  - Only SPA-owned turns persist (the tab holds the stream + writes the
    chat record back). Raw-API kicks leak the concurrency slot when their
    client fetch dies: turn stub stays empty, slot held, everything else
    gets MODEL_CONCURRENCY_LIMIT.
  - The composer submit goes mute while the SPA shows an error state
    ("No response, Please try again later.") after a capacity rejection —
    reload the tab to clear it.
  - React state syncs from Input.insertText (input events) but NOT from
    draft restores: always clear -> focus -> insert fresh.
Usage: native_resubmit.py <chat-id> <message-file> [--label NAME]
Exit 0 = turn live (busy or delta frames seen); 1 = rejected/timeout.
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

WATCH_JS = """(() => {
  window.__stream = '';
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
})()"""

BUSY_JS = ("(() => { const btns = Array.from(document.querySelectorAll('button'))"
           ".map(b => (b.innerText||'').trim());"
           " return btns.some(b => /^(Stop|Pause|Halt)$/i.test(b)) ? 1 : 0; })()")


def _find_tab(cid):
    for t in channel.list_tabs():
        if cid in (t.get("url") or ""):
            return t
    return None


def main():
    chat_id = sys.argv[1]
    msg = open(sys.argv[2]).read()
    label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else chat_id[:8]

    for cycle in range(4):
        tab = _find_tab(chat_id)
        if tab is None:
            print("[%s] no tab on chat %s" % (label, chat_id[:8]), flush=True)
            return 1
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
        try:
            # clear any error state + stale draft: reload on cycles > 0
            if cycle > 0:
                try:
                    ws.call("Page.reload", {}, timeout=30)
                    time.sleep(20)
                except Exception:
                    pass
            try:
                ws.call("Page.bringToFront", {}, timeout=10)
            except Exception:
                pass
            try:
                ws.eval(WATCH_JS, timeout=20)
            except Exception as e:
                print("[%s] patch failed: %s — retry cycle" % (label, str(e)[:60]), flush=True)
                time.sleep(15)
                continue

            # clean composer cycle: clear -> focus -> insert
            print("[%s] clear: %s" % (label, ws.eval(channel.CLEAR_JS, timeout=15)), flush=True)
            time.sleep(0.5)
            ws.eval("(() => { const i = document.querySelector('#chat-input, textarea');"
                    " if (i) { i.focus(); return 'ok'; } return 'gone'; })()", timeout=15)
            time.sleep(0.3)
            ws.call("Input.insertText", {"text": msg})
            time.sleep(2.5)
            vlen = ws.eval("(document.querySelector('textarea')||{value:''}).value.length", timeout=15)
            print("[%s] inserted %s chars" % (label, vlen), flush=True)
            print("[%s] submit: %s" % (label, ws.eval(channel.SUBMIT_JS, timeout=15)), flush=True)

            for i in range(24):
                time.sleep(5)
                try:
                    stream = ws.eval('(window.__stream || "").slice(-350)', timeout=10)
                    ta = ws.eval("(document.querySelector('textarea')||{value:''}).value.length", timeout=10)
                    busy = ws.eval(BUSY_JS, timeout=10)
                except Exception:
                    continue
                print("[%s] %d | taLen:%s busy:%s | %s" % (label, i, ta, busy,
                      (stream or "")[:200].replace("\n", " ")), flush=True)
                if busy == 1 or (stream and "delta_content" in stream):
                    print("[%s] >>> TURN IS LIVE <<<" % label, flush=True)
                    return 0
                if stream and "MODEL_CONCURRENCY" in stream:
                    print("[%s] >>> SLOT STILL HELD — cycle again <<<" % label, flush=True)
                    break
                if stream and "FRONTEND_CAPTCHA" in stream:
                    print("[%s] >>> CAPTCHA REJECTED — cycle again <<<" % label, flush=True)
                    break
            else:
                # no verdict: submit went mute (error state) — reload next cycle
                print("[%s] submit mute — reloading next cycle" % label, flush=True)
                continue
            time.sleep(30)  # back off before next cycle
        finally:
            ws.close()
    print("[%s] exhausted cycles" % label, flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
