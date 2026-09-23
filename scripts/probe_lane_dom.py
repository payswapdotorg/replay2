#!/usr/bin/env python3
"""probe_lane_dom.py — deep DOM state probe for a queued lane tab.

Read-only: reports URL, dialog text, visible buttons, and any
capacity/queue/limit language in the page body, plus body char count.

Usage: probe_lane_dom.py <url-fragment>   (e.g. b90ee795 or all)
"""
import json
import sys

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

JS = r"""
(function(){
  var out = {url: location.href, chars: document.body.innerText.length, dialogText: '', buttons: [], hits: []};
  var dlg = document.querySelector('[role=dialog]');
  if (dlg) out.dialogText = dlg.innerText.slice(0, 300);
  var seen = {};
  document.querySelectorAll('button').forEach(function(b){
    var t = (b.innerText || '').trim();
    if (t && t.length < 40 && !seen[t]) { seen[t] = 1; out.buttons.push(t); }
  });
  var body = document.body.innerText;
  var keys = ['capacity', 'queue', 'busy', 'limit', 'high demand', 'try again', 'later', 'currently'];
  keys.forEach(function(k){
    var i = body.toLowerCase().indexOf(k);
    if (i >= 0) out.hits.push(k + ' :: ' + body.slice(Math.max(0, i - 70), i + 90).replace(/\n/g, ' | '));
  });
  out.tail = body.slice(-400);
  return JSON.stringify(out);
})()
"""


def main():
    frag = sys.argv[1] if len(sys.argv) > 1 else "all"
    for t in channel.list_tabs():
        u = t.get("url") or ""
        if "/c/" not in u:
            continue
        if frag != "all" and frag not in u:
            continue
        try:
            c = channel.CDP(t["webSocketDebuggerUrl"], timeout=15)
            raw = c.eval(JS, timeout=15)
            c.close()
            d = json.loads(raw)
        except Exception as e:
            print(f"== {u[:60]}  PROBE ERROR: {e}")
            continue
        print(f"== {d['url'][:75]}  chars={d['chars']}")
        if d["dialogText"]:
            print("   DIALOG:", d["dialogText"][:280].replace("\n", " | "))
        print("   BUTTONS:", ", ".join(d["buttons"][:14]) or "(none)")
        for h in d["hits"][:6]:
            print("   HIT:", h)
        print("   TAIL:", d["tail"][-260:].replace("\n", " | "))
        print()


if __name__ == "__main__":
    main()
