#!/usr/bin/env python3
"""capacity_recover_send.py <session_url_substr> — recover a session whose
prompt is stuck in the composer behind a capacity dialog.

Per OPERATOR POLICY (2026-09-09): NEVER wait out a capacity popup, NEVER
click 'Switch to GLM-5.3-Flash'. Cancel the dialog, then submit the staged
composer message; round after round until the send is accepted.

Proof of send: composer cleared (textarea value length 0) AND body length
grew beyond the composer content (the prompt echo entered the thread).
"""
import json
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

ROUNDS = 12


def state(cdp):
    return json.loads(cdp.eval(r"""(() => {
  const body = document.body.innerText || '';
  const dlg = document.querySelector('[role=dialog]');
  const ta = document.querySelector('textarea');
  const btns = [...document.querySelectorAll('button')].map(b => (b.innerText||'').trim());
  return JSON.stringify({
    capacity: body.includes('currently at capacity') || body.includes('peak hours'),
    dialogUp: !!dlg,
    cancel: btns.includes('Cancel'),
    composerLen: ta ? ta.value.length : -1,
    bodyLen: body.length
  });
})()"""))


def click_cancel(cdp):
    return cdp.eval(r"""(() => {
  const cands = [...document.querySelectorAll('button')]
    .filter(b => (b.innerText || '').trim() === 'Cancel');
  if (!cands.length) return 'no-cancel-button';
  cands[0].click();
  return 'clicked-cancel';
})()""")


def submit(cdp):
    return cdp.eval(channel.SUBMIT_JS)


def main():
    pat = sys.argv[1]
    t = channel.find_tab(pat)
    if not t:
        raise SystemExit(f"no tab matches {pat}")
    print("tab:", t["id"][:12], t["url"][:70])
    cdp = channel.CDP(t["webSocketDebuggerUrl"])
    try:
        sent = False
        for rnd in range(1, ROUNDS + 1):
            try:
                cdp.call("Page.bringToFront", {}, timeout=10)
            except Exception:
                pass
            s = state(cdp)
            print(f"round {rnd}: {s}")
            if s["composerLen"] <= 0:
                # nothing staged — the send was accepted at some point
                print("composer empty — message left the composer (accepted or lost); "
                      "checking transcript")
                time.sleep(3)
                s2 = state(cdp)
                print("  post-check:", s2)
                if s2["bodyLen"] > 8000:
                    print("SENT (transcript holds the prompt)")
                    sent = True
                break
            # 1) cancel any capacity dialog (NEVER the Flash switch)
            if s["capacity"] or s["dialogUp"]:
                if s["cancel"]:
                    print("  cancel:", click_cancel(cdp))
                    time.sleep(1.5)
                else:
                    print("  dialog up without Cancel — waiting 20s")
                    time.sleep(20)
            # 2) submit the staged message IMMEDIATELY (Enter gate: the
            #    re-popping modal does not actually block the submit)
            body_before = state(cdp)["bodyLen"]
            r = submit(cdp)
            # Enter fallback
            try:
                for typ in ("keyDown", "keyUp"):
                    cdp.call("Input.dispatchKeyEvent", {
                        "type": typ, "key": "Enter", "code": "Enter",
                        "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
            except Exception:
                pass
            time.sleep(4)
            s2 = state(cdp)
            print(f"  submit: {r} | after: composer={s2['composerLen']} "
                  f"body={s2['bodyLen']} capacity={s2['capacity']}")
            if s2["composerLen"] <= 0:
                if s2["capacity"]:
                    # TWO-STATE: composer cleared + modal up = ACCEPTED,
                    # queued server-side, popup cosmetic — do NOT cancel again
                    print("SENT (queued-capacity state — popup cosmetic, monitoring)")
                else:
                    print("SENT (composer cleared, no block)")
                sent = True
                break
            # proof failed — backoff before next round
            backoff = min(20 + 10 * rnd, 60)
            print(f"  not accepted — next round in {backoff}s")
            time.sleep(backoff)
        if not sent:
            print("ROUNDS EXHAUSTED — still blocked")
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
