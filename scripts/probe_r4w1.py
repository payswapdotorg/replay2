#!/usr/bin/env python3
"""Probe all 4 r4-w1 ladder chats for generation state."""
import json, os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel

CHATS = {
    "290f0a1c": "r4-w1b(recreated 17:49)",
    "9b54ebd6": "r4-w1c(17:55)",
    "b7065791": "r4-w1d(18:00)",
    "cebb2e50": "r4-w1e(18:06)",
}

for pfx, label in CHATS.items():
    tab = channel.find_tab(pfx)
    if tab is None:
        print(f"{label}: NO TAB")
        continue
    cdp = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        raw = cdp.eval("""
(() => {
  const body = document.body.innerText || '';
  const streaming = ['Thinking', 'Generating', 'typing…', 'Thought Process'].some(m => body.includes(m));
  const stopBtn = !!document.querySelector('[aria-label*="Stop" i], button[class*="stop" i]');
  const noresp = body.includes('No response');
  const landing = body.includes('Need a assistant') || body.includes('Create anything you can imagine');
  return JSON.stringify({streaming, stopBtn, noresp, landing, len: body.length});
})()""", timeout=20)
        st = json.loads(raw)
        print(f"{label}: len={st['len']} streaming={st['streaming']} stopBtn={st['stopBtn']} noresp={st['noresp']} landing={st['landing']}")
    except Exception as e:
        print(f"{label}: probe error {str(e)[:80]}")
    finally:
        cdp.close()
