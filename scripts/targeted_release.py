#!/usr/bin/env python3
"""targeted_release.py — release ONE dashboard sandbox row by title substring.

Lesson-172-adjacent tooling: the operator rule says release the session you
no longer need; dash_sandbox_release.py releases all non-Live rows (or with
--force ALL rows including live ones — too blunt when a live DUPLICATE of
merged work sits beside a live REAL worker). This tool clicks the Release
button of ONLY the row whose text matches NEEDLE, regardless of Live badge.

Usage: targeted_release.py <title-substring>
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

DASH = "https://chat.z.ai/settings/dashboard"

RELEASE_ONE_JS = r"""
(() => {
  const needle = __NEEDLE__;
  const el = Array.from(document.querySelectorAll('div,section,[role=dialog]'))
    .find(e => (e.innerText||'').includes('Sandbox'));
  const scope = el || document;
  let hit = null;
  scope.querySelectorAll('button').forEach(b => {
    if (((b.innerText || '').trim()) !== 'Release') return;
    const row = b.closest('tr, div');
    const txt = (row ? row.innerText : '') || '';
    if (txt.includes(needle) && !hit) hit = b;
  });
  if (!hit) return JSON.stringify({clicked: 0, err: 'no matching row'});
  const rowTxt = (hit.closest('tr, div') || {}).innerText || '';
  hit.click();
  return JSON.stringify({clicked: 1, row: rowTxt.slice(0, 120)});
})()
""".replace("__NEEDLE__", json.dumps(sys.argv[1] if len(sys.argv) > 1 else ""))


def main():
    needle = sys.argv[1]
    for t in channel.list_tabs():
        if "settings/dashboard" in (t.get("url") or ""):
            break
    else:
        t = channel.new_tab(DASH)
        time.sleep(4)
    c = channel.CDP(t["webSocketDebuggerUrl"], timeout=30)
    r = json.loads(c.eval(RELEASE_ONE_JS, timeout=25))
    print("RELEASE:", r)
    if r.get("clicked"):
        time.sleep(2.5)
        r2 = json.loads(c.eval(RELEASE_ONE_JS, timeout=25))
        print("SECOND PASS (should be no-match):", r2)
    c.close()
    for tb in channel.list_tabs():
        if "settings/dashboard" in (tb.get("url") or ""):
            urllib.request.urlopen(
                f"http://127.0.0.1:9222/json/close/{tb['id']}", timeout=5).read()
            break
    return 0 if r.get("clicked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
