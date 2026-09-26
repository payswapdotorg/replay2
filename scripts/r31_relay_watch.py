#!/usr/bin/env python3
"""r31_relay_watch.py — drive the R31 relay turn to completion.

The relay turn (evidence/r31/** + bundle -> workspace storage root) stalls
on the capacity wall / silent run deaths. This loop:
  - probes the worker tab DOM (block count, RELAY DONE, capacity banner)
  - if frozen for >=2 cycles: cancel popup (never Flash) + send the relay
    nudge
  - checks the workspace git log for new snapshots (relay surfaces only
    after a snapshot checkpoint)
  - SUCCESS when the DOM shows 'RELAY DONE' AND a new snapshot exists
    (or the tree grows relay artifacts); exits 0
"""
import json
import subprocess
import sys
import time

sys.path.insert(0, "/home/z/replay2/scripts")
import channel  # noqa: E402

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
WS = "ws-4271fea0-4b06-4e1c-9706-460696d33939"
CHAT_SUB = "5c7dd782"
CHAT_ID = "5c7dd782-9fff-478f-8c09-aa9efcf68076"
LOG = f"{BASE}/logs/r31-relay-watch.log"
CYCLE_S = 90
FREEZE_NUDGE_AFTER = 3   # cycles frozen before nudging
HORIZON_S = 2 * 3600

NUDGE = ("The capacity wall ate the turn again — retry now (never switch "
         "models). Continue the RELAY exactly per the lead relay nudge in "
         "this transcript: write every evidence/r31/ file (same relative "
         "paths), webflix-r31-gaps.bundle, and RELAY-MANIFEST.txt (file "
         "list + sha256 + lane SHAs) into the WORKSPACE STORAGE ROOT (the "
         "dir your file tools write to — where package.json/src/ live). "
         "When done reply: RELAY DONE + file count.\n")

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  const btns = [...document.querySelectorAll('button')].map(b => (b.innerText||'').trim()).filter(b => /^(Ran|Explored|Wrote)/.test(b));
  return JSON.stringify({len: t.length, n: btns.length, relayDone: t.includes('RELAY DONE'),
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
        if not tabs:
            return {"err": "NOTAB"}
        c = channel.CDP(tabs[0]["webSocketDebuggerUrl"], timeout=15)
        try:
            return json.loads(c.eval(JS_STATE, timeout=20, await_promise=True))
        finally:
            c.close()
    except Exception as e:
        return {"err": str(e)[:120]}


def relay_artifacts():
    """Count relay files visible in the workspace tree."""
    try:
        p = subprocess.run(
            [PY, f"{BASE}/r31_harvest.py", "ls", WS],
            capture_output=True, text=True, timeout=90)
        d = json.loads(p.stdout)
        paths = json.loads(d.get("body", "[]"))
        return [q for q in paths if ("evidence/" in q or "r31" in q.lower()
                                     or "RELAY" in q or "bundle" in q.lower())]
    except Exception as e:
        log(f"ls fail: {str(e)[:80]}")
        return []


def snapshot_count():
    try:
        p = subprocess.run(
            [PY, f"{BASE}/r31_harvest.py", "log", WS],
            capture_output=True, text=True, timeout=90)
        d = json.loads(json.loads(p.stdout)["body"])
        return len(d.get("data", []))
    except Exception as e:
        log(f"log fail: {str(e)[:80]}")
        return -1


def cancel_popup():
    p = subprocess.run([PY, f"{BASE}/r30b_cancel_popup.py", CHAT_SUB],
                       capture_output=True, text=True, timeout=60)
    return (p.stdout or "").strip()[:100]


def send_nudge():
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(NUDGE)
        path = f.name
    try:
        p = subprocess.run([PY, f"{BASE}/manual_send.py", CHAT_SUB, path],
                           capture_output=True, text=True, timeout=120)
        return "SENT-VERIFIED" in (p.stdout or "")
    finally:
        os.unlink(path)


def main():
    t0 = time.time()
    n = 0
    frozen = 0
    last_n = None
    snaps0 = snapshot_count()
    log(f"relay-watch start (snapshots={snaps0})")
    while time.time() - t0 < HORIZON_S:
        n += 1
        st = dom_state()
        if "err" in st:
            log(f"cycle {n}: probe fail {st['err'][:80]}")
        else:
            arts = relay_artifacts()
            log(f"cycle {n}: len={st['len']} n={st['n']} relayDone={st['relayDone']} "
                f"cap={st['cap']} popup={st['popup']} artifacts={len(arts)}")
            if st.get("popup"):
                log("popup -> cancel (never Flash)")
                log(cancel_popup())
                time.sleep(4)
            # progress?
            if last_n is not None and st["n"] != last_n:
                frozen = 0
            else:
                frozen += 1
            last_n = st["n"]
            # SUCCESS: relay done + artifacts visible (or relayDone + snapshot)
            if st["relayDone"] and (arts or snapshot_count() > snaps0):
                log("SUCCESS — RELAY DONE + artifacts/snapshot present")
                return 0
            if arts:
                log(f"artifacts in tree: {arts[:6]}")
                if st["relayDone"]:
                    log("SUCCESS — relay done with artifacts")
                    return 0
            if frozen >= FREEZE_NUDGE_AFTER and not st["relayDone"]:
                if send_nudge():
                    log(f"freeze {frozen} cycles -> relay nudge SENT-VERIFIED")
                    frozen = 0
        time.sleep(CYCLE_S)
    log("HORIZON reached")
    return 1


if __name__ == "__main__":
    sys.exit(main())
