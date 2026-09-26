#!/usr/bin/env python3
"""r31_fix_watch.py — watch for the R31-FIX completion (require-changes round).

Success = the DOM shows '=== R31-FIX COMPLETION REPORT ===' AND the workspace
tree carries fresh relay artifacts (a new RELAY-MANIFEST.txt referencing the
new head). Handles stalls: cancel popups, nudge on freeze.
"""
import json
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
CHAT_SUB = "5c7dd782"
WS = "ws-4271fea0-4b06-4e1c-9706-460696d33939"
LOG = f"{BASE}/logs/r31-fix-watch.log"
MARKER = "R31-FIX COMPLETION REPORT"
CYCLE_S = 90
FREEZE_NUDGE_AFTER = 4
HORIZON_S = 3 * 3600

NUDGE = ("The wall ate the turn again — retry now (never switch models). "
         "Continue the R31-FIX per the lead review nudge in this transcript "
         "(the glyph swap + tests + corpus erratum + scoped gates + fresh "
         "bundle relay). Reply with the marker when done.\n")

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  const btns = [...document.querySelectorAll('button')].map(b => (b.innerText||'').trim()).filter(b => /^(Ran|Explored|Wrote)/.test(b));
  return JSON.stringify({len: t.length, n: btns.length, fixDone: t.includes('""" + MARKER + """'),
                         cap: t.includes('Model is currently at capacity'),
                         popup: [...document.querySelectorAll('button, [role=button]')]
                           .some(b => String(b.innerText||'').trim() === 'Switch to GLM-5.3-Flash')});
})()
"""


def log(m):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}", flush=True)


def dom_state():
    try:
        tabs = [t for t in channel.list_tabs() if CHAT_SUB in (t.get("url") or "")]
        for t in tabs:
            try:
                c = channel.CDP(t["webSocketDebuggerUrl"], timeout=12)
                try:
                    return json.loads(c.eval(JS_STATE, timeout=18, await_promise=True))
                finally:
                    c.close()
            except Exception:
                continue
        return {"err": "all-tabs-dead"}
    except Exception as e:
        return {"err": str(e)[:100]}


def manifest_head():
    """Read the relayed manifest's head SHA (empty until re-relayed)."""
    try:
        p = subprocess.run(
            [PY, f"{BASE}/r31_harvest.py", "fetch", WS,
             "RELAY-MANIFEST.txt", "/tmp/r31-manifest-probe.txt"],
            capture_output=True, text=True, timeout=120)
        if "saved:" not in p.stdout:
            return None
        txt = open("/tmp/r31-manifest-probe.txt").read()
        for line in txt.splitlines():
            if "branch head" in line and ":" in line:
                return line.split(":")[-1].strip()[:12]
    except Exception:
        return None
    return None


def cancel_popup():
    p = subprocess.run([PY, f"{BASE}/r30b_cancel_popup.py", CHAT_SUB],
                       capture_output=True, text=True, timeout=60)
    return (p.stdout or "").strip()[:80]


def send_nudge():
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(NUDGE)
        path = f.name
    try:
        p = subprocess.run([PY, f"{BASE}/manual_send.py", CHAT_SUB, path],
                           capture_output=True, text=True, timeout=120)
        return "SENT-VERIFY" in (p.stdout or "").replace("SENT-VERIFIED", "SENT-VERIFY")
    finally:
        os.unlink(path)


def main():
    t0 = time.time()
    n = 0
    frozen = 0
    last_n = None
    log("fix-watch start")
    while time.time() - t0 < HORIZON_S:
        n += 1
        st = dom_state()
        if "err" in st:
            log(f"cycle {n}: {st['err'][:60]}")
        else:
            log(f"cycle {n}: len={st['len']} n={st['n']} fixDone={st['fixDone']} "
                f"cap={st['cap']} popup={st['popup']}")
            if st.get("popup"):
                log("popup -> cancel")
                log(cancel_popup())
                time.sleep(4)
            if last_n is not None and st["n"] != last_n:
                frozen = 0
            else:
                frozen += 1
            last_n = st["n"]
            # strong truth first: the manifest head change (no echo false-fire)
            head = manifest_head()
            if head and head != "ac852c3529de":
                log(f"SUCCESS — fresh relay manifest (head {head})")
                return 0
            if st["fixDone"]:
                log("fixDone=True in DOM (the nudge echo carries the marker "
                    "string — the manifest probe above is the truth)")
                if n % 10 == 0:
                    log("fixDone but manifest unchanged — the relay may lag; nudging")
                    if send_nudge():
                        log("relay nudge sent")
            elif frozen >= FREEZE_NUDGE_AFTER:
                if send_nudge():
                    log(f"freeze {frozen} -> nudge SENT")
                    frozen = 0
        time.sleep(CYCLE_S)
    log("HORIZON")
    return 1


if __name__ == "__main__":
    sys.exit(main())
