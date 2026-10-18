#!/usr/bin/env python3
"""Watch mer-B for generation start after delivery nudge."""
import json, os, sys, time
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel

MERB = "7b4c016d-4410-4a43-967d-fa597b14e615"

for i in range(12):  # ~6 min
    tab = channel.find_tab(MERB)
    if tab is None:
        print(f"[{i}] no tab"); time.sleep(30); continue
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const noresp = body.includes('No response');
  const msgs = document.querySelectorAll('[class*="message"], [data-role]');
  const last = body.slice(-400);
  return JSON.stringify({len: body.length, stopBtn, noresp, last});
})()""", timeout=20)
        st = json.loads(raw)
        print(f"[{i}] len={st['len']} stopBtn={st['stopBtn']} noresp={st['noresp']}")
        print("    TAIL:", st['last'][-300:].replace('\n', ' | '))
    except Exception as e:
        print(f"[{i}] probe error {e}")
    finally:
        cdp.close()
    time.sleep(30)
