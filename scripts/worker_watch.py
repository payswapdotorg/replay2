#!/usr/bin/env python3
"""worker_watch.py — DOM-growth monitor for live agent-mode worker chats.

The ONLY honest liveness probe for agent-mode chats is TAB DOM (the chats-API
message tree never reflects agent turns). This daemon samples the DOM length
of the pinned view tabs every POLL_S seconds and logs growth. Sustained
growth = GENERATING (turn spawned); static = still queued (corpse check is
the TL's call later).

Usage (lesson-147 orphan idiom):
  bash -c 'cd /home/z/replay2/scripts && setsid nohup python3 \
      worker_watch.py <tag> <chatUrl1> <chatUrl2> [...] \
      < /dev/null > logs/worker_watch_<tag>.log 2>&1 &'
"""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

CDP_HTTP = "http://127.0.0.1:9222/json"
POLL_S = 60
MAX_HOURS = float(__import__("os").environ.get("MAX_HOURS", "8"))


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def list_tabs():
    with urllib.request.urlopen(CDP_HTTP, timeout=10) as r:
        return json.load(r)


def find_tab(url_frag):
    for t in list_tabs():
        if t.get("type") == "page" and url_frag in (t.get("url") or ""):
            return t
    return None


def open_tab(url):
    req = urllib.request.Request(
        CDP_HTTP + "/new?url=" + urllib.parse.quote(url, safe=""), method="PUT")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def dom_len(tab):
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=20)
        try:
            c.call("Runtime.enable", {}, timeout=10)
            v = c.eval("document.documentElement.outerHTML.length", timeout=15)
            return int(v) if v is not None else None
        finally:
            c.close()
    except Exception as e:  # noqa: BLE001
        log("dom probe failed on %s: %s" % (tab["id"][:8], e))
        return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    tag = sys.argv[1]
    chat_urls = sys.argv[2:]
    log("worker_watch armed: tag=%s chats=%d poll=%ds max=%.1fh"
        % (tag, len(chat_urls), POLL_S, MAX_HOURS))
    # ensure one view tab per chat (idempotent)
    tabs = {}
    for u in chat_urls:
        frag = u.rsplit("/", 1)[-1][:8]
        t = find_tab(frag)
        if t is None:
            t = open_tab(u)
            time.sleep(6)
            t = find_tab(frag) or t
        tabs[u] = t["id"]
        log("watching %s on tab %s" % (frag, t["id"][:8]))
    deadline = time.time() + MAX_HOURS * 3600
    last = {u: None for u in chat_urls}
    gen_announced = {u: False for u in chat_urls}
    last_growth = {u: 0.0 for u in chat_urls}
    while time.time() < deadline:
        time.sleep(POLL_S)
        for u in chat_urls:
            t = find_tab(u.rsplit("/", 1)[-1][:8])
            if t is None:
                # tab closed externally; reopen (the worker may have finished)
                t = open_tab(u)
                time.sleep(6)
                t = find_tab(u.rsplit("/", 1)[-1][:8])
                if t is None:
                    log("cannot re-open view tab for %s — skipping round" % u[:40])
                    continue
            n = dom_len(t)
            if n is None:
                continue
            prev = last[u]
            last[u] = n
            if prev is None:
                log("%s baseline DOM=%d" % (u.rsplit('/', 1)[-1][:8], n))
                continue
            if n != prev:
                last_growth[u] = time.time()
                if not gen_announced[u]:
                    gen_announced[u] = True
                    log("%s DOM GROWTH %d -> %d — GENERATING" % (u.rsplit('/', 1)[-1][:8], prev, n))
            else:
                age = int(time.time() - last_growth[u]) if last_growth[u] else -1
                # periodic quiet status
                if int(time.time()) % 1800 < POLL_S:
                    log("%s DOM static at %d (quiet %ss)" % (u.rsplit('/', 1)[-1][:8], n, age))
    log("MAX_HOURS reached — exiting")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
