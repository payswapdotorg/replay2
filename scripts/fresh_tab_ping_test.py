#!/usr/bin/env python3
"""fresh_tab_ping_test.py — discriminator: fresh-renderer vs agent-mode.

Question (2026-10-09 09:2xZ): fresh agent-tab sends fail (status-0 fetch,
silent hang); reload wedges renderers; the PROBE's OLD tab gets regular-mode
replies. Is the broken layer (a) fresh renderers entirely, or (b) agent-mode
backend only?

Test: open a FRESH tab on the small junk chat (regular mode), patch fetch,
type a short ping via the SPA composer, submit, watch 90s for delta frames.
  - delta frames => fresh renderers CAN send regular-mode => broken layer
    is agent-mode backend (W3 = patience on site healing).
  - silent hang => fresh renderers are broken for sends entirely (W3 =
    patience; also explains reload-wedge as fresh-load fetch failure).
Read-only w.r.t. automation; junk chat only.
"""
import os
import sys
import time

BASE = "/home/z/replay2/scripts"
sys.path.insert(0, BASE)
import channel  # noqa: E402

JUNK = "b75f9742-0fc9-4322-a09c-386852d8f77d"

WATCH_JS = """(() => {
  window.__stream = '';
  if (!window.__origFetch) {
    window.__origFetch = window.fetch;
    window.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.includes('/api/v2/chat/completions')) {
        try {
          const r = await window.__origFetch(input, init);
          const ct = r.headers.get('content-type') || '';
          if (ct.includes('event-stream')) {
            const reader = r.body.getReader(); const dec = new TextDecoder();
            (async () => {
              while (true) {
                const {done, value} = await reader.read().catch(() => ({done: true}));
                if (value) { const s = dec.decode(value); window.__stream = (window.__stream + s).slice(-3000); }
                if (done) break;
              }
            })();
          } else { window.__stream = 'nonSSE:' + (await r.text()).slice(0, 400); }
          return r;
        } catch (e) { window.__stream = 'fetcherr:' + String(e).slice(0, 200); throw e; }
      }
      return window.__origFetch(input, init);
    };
    return 'patched';
  }
  return 'already-patched';
})()"""


def main():
    tab = channel.new_tab("https://chat.z.ai/c/%s" % JUNK)
    print("[ping] fresh tab %s on junk chat" % tab["id"][:8], flush=True)
    # wait for the page to settle (readiness poll like v3.1)
    ws = None
    for attempt in range(8):
        time.sleep(10)
        try:
            t2 = {t["id"]: t for t in channel.list_tabs()}.get(tab["id"], tab)
            ws = channel.CDP(t2["webSocketDebuggerUrl"], timeout=20)
            blen = ws.eval("(document.body.innerText || '').length", timeout=8)
            print("[ping] attempt %d body len %s" % (attempt, blen), flush=True)
            if blen and int(blen) > 500:
                break
            ws.close()
            ws = None
        except Exception as e:
            print("[ping] attempt %d not ready: %s" % (attempt, str(e)[:50]), flush=True)
            try:
                ws.close()
            except Exception:
                pass
            ws = None
    if ws is None:
        print("[ping] VERDICT: fresh tab renderer never stabilized (wedge)")
        return 3
    try:
        print("[ping] patch: %s" % ws.eval(WATCH_JS, timeout=15), flush=True)
        ws.eval(channel.CLEAR_JS, timeout=10)
        time.sleep(0.5)
        ws.eval("(() => { const i = document.querySelector('#chat-input, textarea');"
                " if (i) { i.focus(); return 'ok'; } return 'gone'; })()", timeout=10)
        ws.call("Input.insertText", {"text": "ping"})
        time.sleep(2)
        print("[ping] submit: %s" % ws.eval(channel.SUBMIT_JS, timeout=10), flush=True)
        for i in range(18):
            time.sleep(5)
            try:
                s = ws.eval('(window.__stream || "").slice(-300)', timeout=10)
            except Exception as e:
                print("[ping] t+%d eval fail %s" % (i, str(e)[:40]), flush=True)
                continue
            print("[ping] t+%d | %s" % (i, (s or "")[:170].replace("\n", " ")), flush=True)
            if s and "delta_content" in s:
                print("[ping] VERDICT: FRESH-TAB REGULAR-MODE SEND WORKS "
                      "=> broken layer is AGENT-MODE backend")
                return 0
            if s and s.startswith(("fetcherr:", "nonSSE:")):
                print("[ping] VERDICT: fetch FIRED but errored: %s" % s[:120])
                return 2
        print("[ping] VERDICT: no stream activity in 90s — fresh-renderer sends dead")
        return 1
    finally:
        try:
            ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
