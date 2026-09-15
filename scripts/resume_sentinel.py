#!/usr/bin/env python3
"""resume_sentinel.py — waits out the hung turn on the dep-010 chat (5c355d3c),
then fires the staged resume note the moment the composer unlocks.

Context (2026-09-15 ~17:20 UTC): the Lead accidentally released the pod of the
ONLY real DEP-010 worker mid-turn; the server-side turn hung open (no stop
button, send disabled, staged note locked in the composer). When the platform
times the turn out, the composer unlocks. This sentinel polls the tab, and on
unlock: re-stages the note if the composer is empty, presses Enter (focus-
verified), verifies the send, writes flags/dep-010-resume.marker, exits.

Light by design (OOM pressure): one tab, short evals, no rendering.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
LOG = os.path.join(BASE, "logs", "resume_sentinel.log")
CYCLE_S = 120
MAX_CYCLES = 120  # ~4h

CHAT = "5c355d3c"
NOTE = (
    "STATUS NOTE from the Tech Lead: your sandbox pod was released platform-side "
    "mid-run (not your error); your transcript and plan are intact. A fresh pod "
    "provisions automatically for this chat. Please re-clone payswapdotorg/Zeck "
    "(verify base 6fbe6cb4c3c15115f72b297700e09485f9bda050), rebuild branch "
    "work/DEP-010-developer-console, and resume the DEP-010 work order from your "
    "task plan (pinned tests, verification battery, then commit + tarball + "
    "worklog delivery per the original contract)."
)


def log(*args):
    line = time.strftime("[%H:%M:%S]") + " " + " ".join(str(a) for a in args)
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


STATE_JS = r"""
(() => {
  const body = document.body.innerText || '';
  const ta = document.querySelector('textarea, [contenteditable=true]');
  const val = ta ? (ta.value !== undefined ? ta.value : ta.innerText) : '';
  let sendBtn = null;
  for (const b of document.querySelectorAll('button')) {
    const cls = (b.className || '').toString();
    if (cls.includes('/input:') || cls.includes('input:')) { sendBtn = b; break; }
  }
  const cap = Array.from(document.querySelectorAll('div,section'))
    .some(e => (e.innerText || '').includes('currently at capacity'));
  return JSON.stringify({
    href: location.href.slice(-24),
    composerLen: (val || '').length,
    noteStaged: (val || '').includes('STATUS NOTE from the Tech Lead'),
    noteRendered: body.includes('STATUS NOTE from the Tech Lead'),
    sendDisabled: sendBtn ? sendBtn.disabled : null,
    capacityModal: cap,
    tail: body.slice(-90),
  });
})()
"""


def find_tab():
    for t in channel.list_tabs():
        if CHAT in (t.get("url") or "") and t.get("type") == "page":
            return t
    return None


def ensure_tab():
    t = find_tab()
    if t:
        return t
    t = channel.new_tab(f"https://chat.z.ai/c/{CHAT}-1aaa-40f0-826c-27207e0c81c4")
    time.sleep(10)
    return find_tab() or t


def send_note(c):
    """Focus-verified Enter per the house send discipline."""
    try:
        c.eval(r"""(() => { const ta = document.querySelector('textarea, [contenteditable=true]'); if (ta) { ta.focus(); return 'ok'; } return 'gone'; })()""",
               await_promise=False, timeout=15)
        time.sleep(0.4)
        for typ in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", {
                "type": typ, "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13}, timeout=10)
        return True
    except Exception as e:
        log("send_note err:", str(e)[:60])
        return False


def main():
    log("sentinel up — waiting for composer unlock on", CHAT)
    for cycle in range(1, MAX_CYCLES + 1):
        try:
            tab = ensure_tab()
            c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
            try:
                st = json.loads(c.eval(STATE_JS, await_promise=False, timeout=20))
            finally:
                c.close()
            unlocked = (st.get("sendDisabled") is False)
            if st.get("noteRendered"):
                log(f"cycle {cycle}: NOTE RENDERED — resume in flight")
                with open(os.path.join(FLAGS, "dep-010-resume.marker"), "w") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " note-rendered\n")
                return 0
            if unlocked and st.get("composerLen", 0) >= 400:
                log(f"cycle {cycle}: UNLOCKED — sending staged note")
                c2 = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
                try:
                    send_note(c2)
                finally:
                    c2.close()
                time.sleep(8)
                # verify
                c3 = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
                try:
                    st2 = json.loads(c3.eval(STATE_JS, await_promise=False, timeout=20))
                finally:
                    c3.close()
                log(f"cycle {cycle}: post-send {json.dumps(st2)[:200]}")
                if st2.get("noteRendered"):
                    with open(os.path.join(FLAGS, "dep-010-resume.marker"), "w") as f:
                        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " note-sent\n")
                    log("resume note SENT — exiting")
                    return 0
            elif st.get("composerLen", 0) == 0 and not st.get("capacityModal"):
                log(f"cycle {cycle}: composer empty — re-staging note")
                c2 = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
                try:
                    c2.eval(r"""(() => { const ta = document.querySelector('textarea, [contenteditable=true]'); if (ta) { ta.focus(); return 'ok'; } return 'gone'; })()""",
                            await_promise=False, timeout=15)
                    c2.call("Input.insertText", {"text": NOTE}, timeout=15)
                finally:
                    c2.close()
            else:
                log(f"cycle {cycle}: locked (composer={st.get('composerLen')} "
                    f"sendDisabled={st.get('sendDisabled')} cap={st.get('capacityModal')})")
        except Exception as e:
            log(f"cycle {cycle} ERR: {type(e).__name__} {str(e)[:70]}")
        try:
            with open(os.path.join(FLAGS, "resume_sentinel_heartbeat"), "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        time.sleep(CYCLE_S)
    log("MAX_CYCLES reached — exiting")
    return 4


if __name__ == "__main__":
    sys.exit(main())
