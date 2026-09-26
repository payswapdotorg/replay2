#!/usr/bin/env python3
"""
r30b_finish_loop.py — the operator-doctrine finisher for the R30-B worker.

The capacity popup ("switch to GLM-5.3-Flash") keeps re-landing on the
worker chat during peak hours. Operator rules: NEVER switch models; Cancel
the popup + resend the previous prompt, round after round.

Loop (max 20 rounds, ~20s apart):
  1. if the lane is pushed AND the marker line is posted -> DONE (exit 0)
  2. if the popup is present -> Cancel it (real mouse click)
  3. resend the finish instruction (push the lane + post the marker)
  4. if the page shows 'No response' -> the generation route degraded,
     keep the rounds going (the VPN keeps the browser path alive)
"""
import json
import subprocess
import sys
import time

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
SUB = "dd5c60bf"
LOG = f"{BASE}/logs/r30b-finish-loop.log"
ROUNDS = 30

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  const btns = [...document.querySelectorAll('button')];
  const cancel = btns.find(b => (b.innerText || '').trim() === 'Cancel');
  const cr = cancel ? cancel.getBoundingClientRect() : null;
  return JSON.stringify({
    popup: t.includes('Switch to GLM-5.3-Flash'),
    cancelAt: cr ? {x: cr.x + cr.width / 2, y: cr.y + cr.height / 2} : null,
    noResp: t.includes('No response'),
    streaming: !!document.querySelector('[class*=generating]'),
    markerCount: (t.match(/=== R30-B COMPLETION REPORT ===/g) || []).length
  });
})()
"""

FINISH_MSG = (
    "Complete the two remaining steps: (1) push wfx/r30/b to origin with "
    "the full commit message, (2) end your report with the line: "
    "=== R30-B COMPLETION REPORT === followed by the lane SHA.\n"
)


def log(m):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {m}", flush=True)


def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def tab_eval(js):
    code = (
        "import sys, json\n"
        "sys.path.insert(0, '/home/z/replay2/scripts')\n"
        "import channel\n"
        f"tabs = [t for t in channel.list_tabs() if '{SUB}' in (t.get('url') or '')]\n"
        "if not tabs:\n"
        "    print('NOTAB')\n"
        "    raise SystemExit\n"
        "c = channel.CDP(tabs[0]['webSocketDebuggerUrl'], timeout=12)\n"
        "try:\n"
        f"    print(c.eval({js!r}, timeout=10))\n"
        "finally:\n"
        "    c.close()\n"
    )
    rc, out = run([PY, "-c", code], timeout=60)
    last = out.strip().splitlines()[-1] if out.strip() else "EVALFAIL"
    return last


def lane_pushed():
    rc, out = run(["git", "-C", "/home/z/webflix", "ls-remote",
                   "--heads", "origin", "wfx/r30/b"], timeout=60)
    return "wfx/r30/b" in out


def cancel_popup(state):
    at = (state.get("cancelAt") or {})
    code = (
        "import sys, json\n"
        "sys.path.insert(0, '/home/z/replay2/scripts')\n"
        "import channel\n"
        f"tabs = [t for t in channel.list_tabs() if '{SUB}' in (t.get('url') or '')]\n"
        "c = channel.CDP(tabs[0]['webSocketDebuggerUrl'], timeout=12)\n"
        "try:\n"
        f"    for typ in ('mousePressed', 'mouseReleased'):\n"
        f"        c.call('Input.dispatchMouseEvent', {{'type': typ, 'x': {at.get('x', 0)}, "
        f"'y': {at.get('y', 0)}, 'button': 'left', 'clickCount': 1}})\n"
        "    print('cancelled')\n"
        "finally:\n"
        "    c.close()\n"
    )
    rc, out = run([PY, "-c", code], timeout=60)
    return "cancelled" in out


def resend():
    with open("/tmp/r30b-finish-auto.md", "w") as f:
        f.write(FINISH_MSG)
    rc, out = run([PY, f"{BASE}/manual_send.py", SUB,
                   "/tmp/r30b-finish-auto.md"], timeout=180)
    return "SENT-VERIFIED" in out


def main():
    log("FINISHER ARMED — cancel+resend per operator doctrine, never Flash")
    for n in range(1, ROUNDS + 1):
        raw = tab_eval(JS_STATE)
        try:
            st = json.loads(raw)
        except Exception:
            log(f"round {n}: eval fail: {raw[:80]}")
            time.sleep(20)
            continue
        log(f"round {n}: {json.dumps(st)[:200]}")
        if lane_pushed():
            log("LANE IS PUSHED on origin")
            return 0
        if st.get("popup") and st.get("cancelAt"):
            ok = cancel_popup(st)
            log(f"  popup cancelled: {ok}")
            time.sleep(2)
        if st.get("streaming"):
            log("  streaming — waiting")
            time.sleep(30)
            continue
        sent = resend()
        log(f"  resend: {sent}")
        time.sleep(20)
    log("rounds exhausted — lead decision")
    return 2


if __name__ == "__main__":
    sys.exit(main())
