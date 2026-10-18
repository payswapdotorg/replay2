#!/usr/bin/env python3
"""Force-recover mer-B's half-dead turn: click Stop, verify composer, report."""
import json, os, sys, time
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel

MERB = "7b4c016d-4410-4a43-967d-fa597b14e615"

tab = channel.find_tab(MERB)
if tab is None:
    print("no mer-B tab — need tab reopen first"); sys.exit(2)
cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
try:
    # pre-state
    pre = json.loads(cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const btns = Array.from(document.querySelectorAll('button'));
  const stop = btns.find(b => /^(Stop|Pause|Halt)$/i.test((b.innerText||'').trim())
      || /stop/i.test(b.getAttribute('aria-label')||''));
  const input = document.querySelector('#chat-input, textarea');
  return JSON.stringify({
    len: body.length,
    hasStop: !!stop,
    stopVisible: stop ? !!(stop.offsetParent) : false,
    stopRect: stop ? JSON.stringify(stop.getBoundingClientRect()) : null,
    inputDisabled: input ? input.disabled : null,
  });
})()""", timeout=20))
    print("PRE:", json.dumps(pre))

    if pre["hasStop"]:
        # click the stop button — kills the half-dead generation
        res = cdp.eval("""
(() => {
  const btns = Array.from(document.querySelectorAll('button'));
  const stop = btns.find(b => /^(Stop|Pause|Halt)$/i.test((b.innerText||'').trim())
      || /stop/i.test(b.getAttribute('aria-label')||''));
  if (!stop) return 'gone';
  stop.click();
  return 'clicked';
})()""", timeout=20)
        print("STOP CLICK:", res)
        time.sleep(4)

    # post-state: stop gone? composer enabled?
    post = json.loads(cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const btns = Array.from(document.querySelectorAll('button'));
  const stop = btns.find(b => /^(Stop|Pause|Halt)$/i.test((b.innerText||'').trim())
      || /stop/i.test(b.getAttribute('aria-label')||''));
  const input = document.querySelector('#chat-input, textarea');
  const sendBtn = btns.find(b => /send/i.test(b.getAttribute('aria-label')||''));
  return JSON.stringify({
    len: body.length,
    hasStop: !!stop,
    inputDisabled: input ? input.disabled : null,
    hasSend: !!sendBtn,
  });
})()""", timeout=20))
    print("POST:", json.dumps(post))
finally:
    cdp.close()
