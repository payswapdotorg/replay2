#!/usr/bin/env python3
"""r31_gen_recovery.py — the generation-retry loop for the R31 worker chat.

Cloned from r30b_gen_recovery.py (the proven R30-B pattern) with the
capacity-wall class added: the thread shows "Model is currently at capacity"
when the nudge's turn fails to fire.

Doctrine (operator): never wait, never Flash — cancel the popup, retry and
retry until the turn fires.

Loop (every ~150s):
  1. read the worker tab's DOM truth (streaming / capacity / noResp / popup)
  2. if streaming OR assistant content beyond the stubs -> SUCCESS, exit 0
  3. cancel the capacity popup if present (never Flash)
  4. send the retry nudge when the wall is clear, or every NUDGE_EVERY-th
     cycle as fallback
  5. if the chat dies (list-miss + detail fail) -> exit 30 for re-dispatch
"""
import json
import subprocess
import sys
import time

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
CHAT_SUB = "5c7dd782"
LOG = f"{BASE}/logs/r31-gen-recovery.log"
CYCLE_S = 150
NUDGE_EVERY = 5          # fallback nudge cadence when the wall persists
HORIZON_S = 3 * 3600

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  const blocks = [...document.querySelectorAll('button')].map(b => (b.innerText||'').trim());
  const ranBlocks = blocks.filter(b => /^(Ran|Explored|Wrote)/.test(b));
  const asst = [...document.querySelectorAll('[class*=message]')]
    .filter(b => (b.className||'').includes('assistant'));
  return JSON.stringify({
    bodyLen: t.length,
    noResp: t.includes('No response'),
    capacity: t.includes('Model is currently at capacity'),
    popup: [...document.querySelectorAll('button, [role=button]')]
      .some(b => String(b.innerText || '').trim() === 'Switch to GLM-5.3-Flash'),
    streaming: !!document.querySelector('[class*=generating], [class*=streaming]'),
    ranN: ranBlocks.length,
    asstText: (asst.length ? (asst[asst.length-1].innerText||'') : '').trim().length
  });
})()
"""

NUDGE = ("Retry the generation now (transient platform capacity error — never "
         "switch models). Continue the R31 build per the packet + the lead "
         "nudge in this transcript.\n")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def dom_state():
    """Read the worker tab DOM via a one-shot CDP eval."""
    code = (
        "import sys, json; sys.path.insert(0, '" + BASE + "'); import channel\n"
        "tabs = [t for t in channel.list_tabs() if '" + CHAT_SUB + "' in (t.get('url') or '')]\n"
        "if not tabs: print('NOTAB'); sys.exit(1)\n"
        "c = channel.CDP(tabs[0]['webSocketDebuggerUrl'], timeout=15)\n"
        "try: print(c.eval(" + repr(JS_STATE) + ", timeout=20, await_promise=True))\n"
        "finally: c.close()\n"
    )
    p = subprocess.run([PY, "-c", code], capture_output=True, text=True, timeout=60)
    out = (p.stdout or "").strip()
    # take the FIRST line that parses as a JSON object (warnings may trail)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return {"err": out[:200] or (p.stderr or "")[:200]}


def cancel_popup():
    p = subprocess.run([PY, f"{BASE}/r30b_cancel_popup.py", CHAT_SUB],
                       capture_output=True, text=True, timeout=60)
    return (p.stdout or "").strip()


def send_nudge(text=NUDGE):
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
        path = f.name
    try:
        p = subprocess.run([PY, f"{BASE}/manual_send.py", CHAT_SUB, path],
                           capture_output=True, text=True, timeout=120)
        return "SENT-VERIFIED" in (p.stdout or "")
    finally:
        os.unlink(path)


def chat_alive():
    p = subprocess.run(
        [PY, f"{BASE}/chats_http.py", "detail",
         "5c7dd782-9fff-478f-8c09-aa9efcf68076"],
        capture_output=True, text=True, timeout=60)
    return "title:" in (p.stdout or "")


def main():
    t0 = time.time()
    n = 0
    log("gen-recovery loop start (R31)")
    last_ran = None
    stable_success = 0
    while time.time() - t0 < HORIZON_S:
        n += 1
        st = dom_state()
        if "err" in st or st.get("bodyLen") is None:
            log(f"cycle {n}: probe-fail {st.get('err','')[:80]}")
        else:
            log(f"cycle {n}: len={st['bodyLen']} ran={st['ranN']} "
                f"cap={st['capacity']} noResp={st['noResp']} "
                f"popup={st['popup']} stream={st['streaming']} "
                f"asstTxt={st['asstText']}")
            # SUCCESS: real activity — streaming, or blocks growing, or
            # assistant prose landed beyond stubs
            if st["streaming"] or st["asstText"] > 200:
                stable_success += 1
                if stable_success >= 2:
                    log("SUCCESS — the turn is live")
                    return 0
            else:
                stable_success = 0
            if st["ranN"] != last_ran and last_ran is not None:
                log(f"SUCCESS — block growth {last_ran}->{st['ranN']}")
                return 0
            last_ran = st["ranN"]
            if st["popup"]:
                log("popup present — cancel (never Flash)")
                log(cancel_popup()[:120])
                time.sleep(5)
                continue
            if st["noResp"] and (n % 2 == 0 or not st["capacity"]):
                # "No response" without capacity = the turn died quietly:
                # retry on alternating cycles
                if send_nudge():
                    log("retry nudge SENT-VERIFIED")
                    time.sleep(CYCLE_S)
                    continue
            if not st["capacity"] and not st["streaming"] and n % 2 == 1:
                # wall clear + nothing running -> the pending turn may need
                # a fresh trigger on odd cycles
                if send_nudge():
                    log("trigger nudge SENT-VERIFIED")
                    time.sleep(CYCLE_S)
                    continue
            elif n % NUDGE_EVERY == 0:
                if send_nudge():
                    log(f"fallback nudge (cycle {n}) SENT-VERIFIED")
        if not chat_alive():
            log("chat DEAD — list-miss + detail fail; re-dispatch needed")
            return 30
        time.sleep(CYCLE_S)
    log("HORIZON reached without revival")
    return 1


if __name__ == "__main__":
    sys.exit(main())
