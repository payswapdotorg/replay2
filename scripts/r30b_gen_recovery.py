#!/usr/bin/env python3
"""
r30b_gen_recovery.py — the generation-retry loop for the R30-B worker chat.

Situation (19:3xZ): dispatch landed, but every generation turn fails with
"No response, Please try again later" (server 5xx degradation, bursty).
Doctrine (operator): never wait — retry and retry, find a way around.

Loop (every ~150s):
  1. read the worker tab's DOM truth (lesson-138: streaming/noResp state)
  2. if streaming OR an assistant response landed -> SUCCESS, exit 0
  3. probe the model menu (platform-health signal): options present = healthy
  4. nudge when healthy, or every NUDGE_EVERY-th cycle as fallback
  5. if the chat dies (list-miss + detail fail) -> exit 30 for re-dispatch
"""
import subprocess
import sys
import time

PY = "/home/z/.venv/bin/python3"
BASE = "/home/z/replay2/scripts"
CHAT = "d5e9e1ec-b980-4c8d-b7b7-45b90c7df2cc"
LOG = f"{BASE}/logs/r30b-gen-recovery.log"
CYCLE_S = 150
NUDGE_EVERY = 5          # fallback nudge cadence when the menu stays empty
HORIZON_S = 2 * 3600

JS_STATE = """
(() => {
  const t = document.body.innerText || '';
  return JSON.stringify({
    bodyLen: t.length,
    noResp: t.includes('No response'),
    streaming: !!document.querySelector('[class*=generating]'),
    assistant: (() => {
      // any assistant-authored block beyond the 'No response' stubs
      const blocks = [...document.querySelectorAll('[class*=message]')];
      return blocks.some(b => (b.className||'').includes('assistant')
                           && (b.innerText||'').trim().length > 100);
    })()
  });
})()
"""

NUDGE = ("Retry the generation now (transient platform error). Execute the "
         "R30-B build per the packet in this transcript.\n")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def tab_state():
    """DOM truth via a python inline run on the worker tab."""
    code = (
        "import sys, time\n"
        "sys.path.insert(0, '/home/z/replay2/scripts')\n"
        "import channel\n"
        f"tabs = [t for t in channel.list_tabs() if '{CHAT[:8]}' in (t.get('url') or '')]\n"
        "if not tabs:\n"
        "    print('NOTAB')\n"
        "    raise SystemExit\n"
        "c = channel.CDP(tabs[0]['webSocketDebuggerUrl'], timeout=12)\n"
        "try:\n"
        f"    print(c.eval({JS_STATE!r}, timeout=10))\n"
        "finally:\n"
        "    c.close()\n"
    )
    rc, out = run([PY, "-c", code], timeout=60)
    return out.strip().splitlines()[-1] if out.strip() else "EVALFAIL"


def menu_healthy():
    rc, out = run([PY, f"{BASE}/model_menu_probe.py"], timeout=90)
    return "GLM-5.3" in out and "ABSENT" not in out


def nudge():
    with open("/tmp/r30b-nudge-auto.md", "w") as f:
        f.write(NUDGE)
    rc, out = run([PY, f"{BASE}/manual_send.py", CHAT[:8],
                   "/tmp/r30b-nudge-auto.md"], timeout=180)
    return "SENT-VERIFIED" in out


def chat_alive():
    rc, out = run([PY, f"{BASE}/chats_http.py", "detail", CHAT], timeout=60)
    return rc == 0 and "title:" in out


def main():
    log("GEN-RECOVERY ARMED — retry turns until generation starts")
    t0 = time.time()
    cycle = 0
    while time.time() - t0 < HORIZON_S:
        cycle += 1
        st = tab_state()
        log(f"cycle {cycle}: {st}")
        if "streaming\":true" in st or "assistant\":true" in st:
            log("GENERATION LIVE — success")
            return 0
        if not chat_alive():
            log("chat died — re-dispatch needed")
            return 30
        healthy = menu_healthy()
        log(f"  platform menu healthy: {healthy}")
        if healthy or cycle % NUDGE_EVERY == 0:
            ok = nudge()
            log(f"  nudge sent: {ok}")
        time.sleep(CYCLE_S)
    log("HORIZON reached — lead decision")
    return 2


if __name__ == "__main__":
    sys.exit(main())
