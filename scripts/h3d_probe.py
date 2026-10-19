#!/usr/bin/env python3
"""h3d_probe.py — one-shot workspace state probe (positions in VIEWPORT coords)."""
import sys
import json

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = r"""(() => {
  const modal = [...document.querySelectorAll('div')].filter(e => {
    const s = getComputedStyle(e);
    return s.position === 'fixed' && e.getBoundingClientRect().width > 500 && (e.textContent||'').includes('80%');
  });
  const agentic = [...document.querySelectorAll('div,span')].filter(e => (e.className||'').toString().includes('agentic') && e.getBoundingClientRect().width > 0);
  const sw = agentic.find(e => { const r = e.getBoundingClientRect(); return r.width > 30 && r.width < 100; });
  let swPos = null;
  if (sw) { const r = sw.getBoundingClientRect(); swPos = {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}; }
  const agenticText = agentic.length ? agentic[0].textContent.trim().slice(0, 80) : null;
  const gen = document.getElementById('rodinGenerateBtn');
  const gr = gen ? gen.getBoundingClientRect() : null;
  const ta = [...document.querySelectorAll('textarea')].filter(t => t.getBoundingClientRect().width > 0);
  return JSON.stringify({
    promoOpen: modal.length > 0,
    agenticSwitch: swPos,
    agenticText,
    genBtn: gr ? {x: Math.round(gr.x + gr.width/2), y: Math.round(gr.y + gr.height/2), txt: (gen.textContent||'').trim().replace(/\n/g, '|').slice(0, 25)} : null,
    textarea: ta.length ? {x: Math.round(ta[0].getBoundingClientRect().x + ta[0].getBoundingClientRect().width/2), y: Math.round(ta[0].getBoundingClientRect().y + ta[0].getBoundingClientRect().height/2), val: ta[0].value.slice(0, 40)} : null,
    scrollY: Math.round(window.scrollY)
  });
})()"""


def main():
    tabs = channel.list_tabs()
    h3d = [t for t in tabs if "hyper3d" in (t.get("url") or "")]
    if not h3d:
        print(json.dumps({"error": "no hyper3d tab"}))
        return
    ws = channel.CDP(h3d[0]["webSocketDebuggerUrl"])
    try:
        print(ws.eval(JS, await_promise=False, timeout=15))
    finally:
        ws.close()


if __name__ == "__main__":
    main()
