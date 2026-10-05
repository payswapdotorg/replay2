#!/usr/bin/env python3
"""w4002_nudge_watch.py — land the staged W4-002 continuation nudge.

State (2026-10-05 09:40Z): the W4-002 worker chat (476b5e05) carries the
full work order as message 1; the original turn never opened (3h dead,
§8-stop cured server-side); a continuation nudge ('EXECUTE NOW ...') is
staged in the composer behind a GLM-5.3 peak-hours capacity dialog.

This daemon owns the never-wait fight (operator policy 2026-09-09):
every CYCLE seconds — cancel the dialog (NEVER the Flash switch),
resubmit the staged composer text (real-mouse send button, Enter
fallback), then classify:
  - composer cleared + capacity modal up  = ACCEPTED-queued (two-state
    law) -> switch to turn-open watch, stop cancelling
  - composer cleared + no modal           = ACCEPTED -> turn-open watch
  - composer still staged                 = fight another round

Exit conditions:
  - server tree grows a content-bearing assistant turn -> LANDED
    (flags/w4002_nudge_landed, exit 0)
  - WINDOW expires (default 12h) -> exit 1 with flags/w4002_nudge_failed

Usage: dfork_launch.py logs/w4002_nudge.log python3 w4002_nudge_watch.py
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

CHAT = "476b5e05-b67c-47f0-8c3f-a5e7cd3c429c"
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "w4002_nudge.log")
CYCLE = 45          # seconds between assault rounds
WINDOW = 12 * 3600  # never-die window
TOK = os.path.join(FLAGS, "chat_token")
NUDGE = ("EXECUTE NOW: the complete P4-W4-002 work order is the first message in this thread "
         "(Build PaySwap Universal Interface, packages/web). Begin immediately and execute it in full "
         "per its own instructions — pinned base, branch, laws, evidence, and the delivery-report "
         "format at the end. The work order is self-contained; do not ask clarifying questions.")


def log(msg):
    line = f"[w4002-nudge {time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


def state(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const body = document.body.innerText || '';
  const ta = document.querySelector('textarea');
  return JSON.stringify({
    composerLen: ta ? ta.value.length : -1,
    bodyLen: body.length,
    capacity: body.includes('currently at capacity') || body.includes('peak hours'),
    cancel: [...document.querySelectorAll('button')].some(b => (b.innerText||'').trim() === 'Cancel'),
    generating: !!document.querySelector('.generating, [class*=generating]')
  });
})()"""))


def click_cancel(cdp):
    return cdp.eval(r"""(() => {
  const c = [...document.querySelectorAll('button')]
    .filter(b => (b.innerText || '').trim() === 'Cancel');
  if (!c.length) return 'none';
  c[0].click(); return 'clicked';
})()""")


def submit(cdp):
    pos = cdp.eval(r"""(() => {
  const b = document.querySelector('button.sendMessageButton');
  if (!b || b.disabled) return '';
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
})()""")
    if pos:
        p = json.loads(pos)
        if p.get("x", 0) > 0:
            cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": p["x"],
                                                  "y": p["y"], "button": "left", "clickCount": 1})
            cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": p["x"],
                                                  "y": p["y"], "button": "left", "clickCount": 1})
            return "real-mouse-send"
    return cdp.eval(channel.SUBMIT_JS)


def tree_state():
    """Server-side truth: (n_msgs, assistant_content_len, latest_ts)."""
    try:
        tok = open(TOK).read().strip()
        req = urllib.request.Request(
            f"https://chat.z.ai/api/v1/chats/{CHAT}",
            headers={"Authorization": "Bearer " + tok,
                     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                   "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"})
        d = json.load(urllib.request.urlopen(req, timeout=20))
        msgs = ((d.get("chat") or {}).get("history") or {}).get("messages") or {}
        best = 0
        for m in msgs.values():
            if m.get("role") == "assistant":
                best = max(best, len(m.get("content") or ""))
        return len(msgs), best
    except Exception as e:
        return -1, -1


def main():
    log(f"armed — chat {CHAT[:8]}, cycle {CYCLE}s, window {WINDOW//3600}h")
    t0 = time.time()
    accepted = False
    while time.time() - t0 < WINDOW:
        try:
            tab = channel.find_tab(CHAT[:8])
            if not tab:
                log("no chat tab — opening one")
                channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
                time.sleep(15)
                continue
            ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
            try:
                s = state(ws)
                if accepted:
                    # turn-open watch: stop assaulting, poll the server tree
                    n, alen = tree_state()
                    if n > 2 or alen > 0:
                        log(f"LANDED — tree n={n} assistant_len={alen}")
                        open(os.path.join(FLAGS, "w4002_nudge_landed"), "w").write(
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                        return 0
                    if s["composerLen"] > 0:
                        log("composer refilled post-accept (site rollback) — resuming assault")
                        accepted = False
                    else:
                        log(f"accepted-queued, waiting for turn open (tree n={n})")
                else:
                    if s["composerLen"] > 0:
                        if s["capacity"] or s["cancel"]:
                            if s["cancel"]:
                                click_cancel(ws)
                                time.sleep(1.5)
                        r = submit(ws)
                        try:
                            for typ in ("keyDown", "keyUp"):
                                ws.call("Input.dispatchKeyEvent", {
                                    "type": typ, "key": "Enter", "code": "Enter",
                                    "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
                        except Exception:
                            pass
                        time.sleep(5)
                        s2 = state(ws)
                        if s2["composerLen"] <= 0:
                            accepted = True
                            log(f"ACCEPTED ({r}) — two-state: capacity={s2['capacity']} "
                                f"(modal cosmetic if true)")
                        else:
                            log(f"round fought ({r}) — composer={s2['composerLen']} "
                                f"capacity={s2['capacity']}")
                    else:
                        # composer empty + not yet accepted: either a prior
                        # round's send landed late, or a Chrome restart ate
                        # the staged text. Tree truth decides.
                        n, alen = tree_state()
                        if n > 2 or alen > 0:
                            log(f"LANDED (late accept — tree n={n} alen={alen})")
                            open(os.path.join(FLAGS, "w4002_nudge_landed"), "w").write(
                                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                            return 0
                        log("composer empty but turn never opened — re-staging nudge")
                        channel._type_into_composer(ws, NUDGE)
                        time.sleep(2)
                    # fall through to the next cycle
            finally:
                ws.close()
        except Exception as e:
            log(f"cycle error: {type(e).__name__}: {e}")
        time.sleep(CYCLE)
    log("WINDOW EXPIRED — nudge never landed")
    open(os.path.join(FLAGS, "w4002_nudge_failed"), "w").write(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
