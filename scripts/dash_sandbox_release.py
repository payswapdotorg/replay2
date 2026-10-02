#!/usr/bin/env python3
"""dash_sandbox_release.py — open settings/dashboard, dump the Sandbox
section rows, and release EVERY held sandbox (safe when no worker is
generating; the operator console session is a chat tab, not a sandbox).

Boot-prompt §16(a): completed sessions' sandboxes linger and hold the
usage limit — release them so the window can clear.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

DASH = "https://chat.z.ai/settings/dashboard"

DUMP_JS = r"""
(() => {
  const all = Array.from(document.querySelectorAll('*'));
  const head = all.find(e => Array.from(e.childNodes)
      .filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ') === 'Sandbox');
  if (!head) return JSON.stringify({err: 'no Sandbox heading'});
  let root = head;
  for (let i = 0; i < 5 && root.parentElement; i++) root = root.parentElement;
  const txt = (root.innerText || '').slice(0, 1500);
  const btns = Array.from(root.querySelectorAll('button'))
      .map(b => (b.innerText || '').trim().slice(0, 30)).filter(Boolean);
  return JSON.stringify({txt: txt, btns: btns.slice(0, 30)});
})()
"""

RELEASE_JS = r"""
(() => {
  // 2026-09-25 live-pod guard (lesson-153): only release rows whose text
  // does NOT carry a Live badge — clicking a Live row's Release button
  // reaps a running worker's sandbox (incident: the ANR-Discovery-Loop pod).
  const el = Array.from(document.querySelectorAll('div,section,[role=dialog]'))
    .find(e => (e.innerText||'').includes('Sandbox'));
  const scope = el || document;
  let clicked = 0, live = 0;
  scope.querySelectorAll('button').forEach(b => {
    if (((b.innerText || '').trim()) !== 'Release') return;
    const row = b.closest('tr, div');
    const txt = (row ? row.innerText : '') || '';
    if (/\bLive\b/.test(txt)) { live += 1; return; }
    b.click();
    clicked += 1;
  });
  return JSON.stringify({clicked: clicked, live_skipped: live});
})()
"""


def open_dash_tab():
    for t in channel.list_tabs():
        if "settings/dashboard" in (t.get("url") or ""):
            return t
    t = channel.new_tab(DASH)
    if t is None:
        raise SystemExit("could not open dashboard tab")
    time.sleep(4)
    return t


def main():
    tab = open_dash_tab()
    c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
    dump = json.loads(c.eval(DUMP_JS, timeout=25))
    if "err" in dump:
        # page may still be loading
        time.sleep(5)
        dump = json.loads(c.eval(DUMP_JS, timeout=25))
    print("SANDBOX SECTION:")
    print(dump.get("txt", "(empty)")[:1200])
    print("BUTTONS:", dump.get("btns", []))
    # release loop: click Release for every NON-LIVE row until none remain
    # (--force overrides the live guard for operator-directed full clears)
    force = "--force" in sys.argv
    total = 0
    for _ in range(12):
        r = json.loads(c.eval(RELEASE_JS, timeout=20))
        if force and r.get("live_skipped"):
            r = {"clicked": r.get("clicked", 0) + r["live_skipped"]}
        if not r.get("clicked"):
            if r.get("live_skipped"):
                print(f"GUARD: skipped {r['live_skipped']} LIVE sandbox(es) "
                      f"(use --force to override)")
            break
        total += r["clicked"]
        time.sleep(2.5)  # let the row vanish / API settle
    print(f"RELEASED: {total} sandbox(es)")
    dump2 = json.loads(c.eval(DUMP_JS, timeout=25))
    print("AFTER:", (dump2.get("txt") or "")[:400])
    c.close()
    # close the dashboard tab (keep the browser tidy)
    for t in channel.list_tabs():
        if "settings/dashboard" in (t.get("url") or ""):
            urllib.request.urlopen(
                f"http://127.0.0.1:9222/json/close/{t['id']}", timeout=5).read()
            break


if __name__ == "__main__":
    main()
