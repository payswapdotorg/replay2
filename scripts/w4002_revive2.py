#!/usr/bin/env python3
"""w4002_revive2.py — land the staged W4-002 CONTINUATION directive.

12:45Z context: the §8 cure closed the wedged turn (worker froze at the
ROOT BATTERY step 10:35Z); a CONTINUE directive (932 chars) is staged in
the composer behind a peak-hours capacity dialog (the send rolled back).

Same never-wait fight as w4002_nudge_watch, but the landing baseline is
the post-cure tree: n=4. LANDED = tree grows beyond 4 (the continuation
turn) OR any assistant content lands. NEVER overwrites the staged text
(the directive stays in the composer across rounds); re-types it only if
the composer goes empty WITHOUT the tree growing (Chrome restart case —
but then the exact directive text must be restored, so it is embedded
here verbatim).

Usage: dfork_launch.py logs/w4002_revive2.log python3 w4002_revive2.py
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
CYCLE = 45
WINDOW = 12 * 3600
N_BASE = 4  # post-cure tree size (2 original + 2 from the morning revival)
TOK = os.path.join(FLAGS, "chat_token")

DIRECTIVE = ("CONTINUE — your turn was interrupted mid-run (you had just printed '=== 4. ROOT BATTERY ===' and were about to "
             "run it). Your sandbox filesystem state PERSISTS: everything you built (packages/web source, tests, evidence) "
             "is still on disk in /home/z/my-project/payswap.org. Resume exactly where you stopped: "
             "(1) run the ROOT BATTERY from the repo root (npm test / the repo's battery command per the work order); "
             "(2) run typecheck + verify:repo; (3) if green, push branch work/P4-W4-002 per the work order's push command; "
             "(4) post your FINAL DELIVERY REPORT in this chat (branch + HEAD SHA, changed files, test receipts, "
             "typecheck + verify:repo results, surface-API placement decision, research-mapping summary, browser-verification "
             "evidence desktop+mobile, honest deviations). Do not redo work already done — verify it, then finish. "
             "If anything you built is missing from disk, rebuild only that part and report the deviation honestly.")


def log(msg):
    print(f"[w4002-r2 {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def state(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const body = document.body.innerText || '';
  const ta = document.querySelector('textarea');
  return JSON.stringify({
    composerLen: ta ? ta.value.length : -1,
    bodyLen: body.length,
    capacity: body.includes('currently at capacity') || body.includes('peak hours'),
    cancel: [...document.querySelectorAll('button')].some(b => (b.innerText||'').trim() === 'Cancel')
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
    """(n_msgs, assistant_content_len)."""
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
    except Exception:
        return -1, -1


def main():
    log(f"armed — continuation assault, N_BASE={N_BASE}, cycle {CYCLE}s, window {WINDOW//3600}h")
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
                    n, alen = tree_state()
                    if n > N_BASE or alen > 0:
                        log(f"LANDED — tree n={n} (base {N_BASE}) alen={alen}")
                        open(os.path.join(FLAGS, "w4002_revive2_landed"), "w").write(
                            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                        return 0
                    if s["composerLen"] > 50:
                        log("composer refilled post-accept (rollback) — resuming assault")
                        accepted = False
                    else:
                        log(f"accepted-queued, waiting for turn open (n={n})")
                else:
                    if s["composerLen"] > 50:
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
                        if s2["composerLen"] <= 10:
                            accepted = True
                            log(f"ACCEPTED ({r}) — capacity={s2['capacity']}")
                        else:
                            log(f"round fought ({r}) — composer={s2['composerLen']} capacity={s2['capacity']}")
                    elif s["composerLen"] >= 0:
                        # empty composer: late landing, Chrome restart, or lost text
                        n, alen = tree_state()
                        if n > N_BASE or alen > 0:
                            log(f"LANDED (late accept — n={n} alen={alen})")
                            open(os.path.join(FLAGS, "w4002_revive2_landed"), "w").write(
                                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                            return 0
                        log("composer empty, turn not open — re-staging directive")
                        channel._type_into_composer(ws, DIRECTIVE)
                        time.sleep(2)
            finally:
                ws.close()
        except Exception as e:
            log(f"cycle error: {type(e).__name__}: {e}")
        time.sleep(CYCLE)
    log("WINDOW EXPIRED")
    open(os.path.join(FLAGS, "w4002_revive2_failed"), "w").write(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
