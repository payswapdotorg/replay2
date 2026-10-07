#!/usr/bin/env python3
"""capture_spa_request.py — capture the FULL completions request the SPA builds.

Patches fetch on a fresh home tab, types a probe message, submits, and
captures the request URL (all query params) + headers + body head before
aborting it. Purpose: diff the SPA's request shape against kick_queued's
reconstruction to find what the F019 captcha validation needs.
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

PATCH = """(() => {
  window.__req = null;
  window.__origFetch = window.fetch;
  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.includes('/api/v2/chat/completions')) {
      let bodyHead = '';
      try { bodyHead = String(init.body).slice(0, 400); } catch (e) {}
      let hdrs = {};
      try {
        const h = new Headers(init.headers || (input && input.headers) || {});
        for (const [k, v] of h.entries()) hdrs[k] = v;
      } catch (e) {}
      window.__req = {url: url, headers: hdrs, bodyHead: bodyHead};
      throw new DOMException('aborted-for-capture', 'AbortError');
    }
    return window.__origFetch(input, init);
  };
  return 'patched';
})()"""


def main():
    tab = channel.new_tab("https://chat.z.ai/")
    if tab is None:
        print("fresh home tab failed")
        return 1
    time.sleep(8)
    tabs = {t["id"]: t for t in channel.list_tabs()}
    t = tabs.get(tab["id"], tab)
    ws = channel.CDP(t["webSocketDebuggerUrl"], timeout=30)
    try:
        ws.eval(PATCH, timeout=10)
        ok = channel._type_into_composer(
            ws, "Probe: analyze the repository state and report the current branch head.")
        print("typed:", ok)
        ws.eval(channel.SUBMIT_JS, timeout=10)
        for _ in range(20):
            time.sleep(1.5)
            got = ws.eval("window.__req ? JSON.stringify(window.__req) : null", timeout=8)
            if got and got != "null":
                print("CAPTURED REQUEST:")
                print(json.dumps(json.loads(got), indent=1)[:3000])
                break
        else:
            print("no completions request captured (submit gated?)")
    finally:
        try:
            ws.eval("window.fetch = window.__origFetch; 'restored'", timeout=8)
        except Exception:
            pass
        ws.close()
        try:
            channel._http_json("/json/close/" + t["id"], method="PUT")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
