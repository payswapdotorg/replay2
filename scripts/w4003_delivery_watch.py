#!/usr/bin/env python3
"""w4003_delivery_watch.py — live-DOM truth watcher for W4-003 (terminal work item).

Replaces the 09:59Z watcher (killed ~16:00Z): that one fired DELIVERED on
branch existence — WRONG under the push-early protocol (the branch now
appears early with skeleton commits) — and its report criterion read the
server record, whose assistant messages store content=None (skeleton-only,
observed all day for chat 476b5e05).

v2 truth model:
  - remote branch head (git ls-remote): PROGRESS signal (first push, HEAD
    advances) — logged, never the completion trigger.
  - LIVE DOM of the worker tab (CDP): the completion trigger. The worker's
    final reports use the heading 'FINAL DELIVERY REPORT'. DELIVERED =
    branch exists beyond base AND the live DOM tail carries the report
    marker AND a 40-hex SHA AND the turn is not generating.
  - STALLED2 (s8 cure candidate): bodyLen static AND not generating AND
    branch HEAD static for STALL_AFTER (90 min). With push-early, a stall
    with a branch on remote means the continuation clones from the branch.
  - WINDOW 14h from arm time.

Usage: dfork_launch.py logs/w4003_delivery.log python3 w4002_delivery_watch2.py
"""
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import channel  # noqa: E402

CHAT = "909254a5-cd98-4397-8507-19f65cc169d2"
BRANCH = "work/P4-W4-003"
BASE_SHA = "bf41475"
REMOTE = "https://github.com/payswapdotorg/payswap.org.git"
FLAGS = os.path.join(BASE, "flags")
CYCLE = 300          # 5 min
STALL_AFTER = 90 * 60
WINDOW = 14 * 3600
SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")


def log(msg):
    print(f"[w4003-dw {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def branch_head():
    """Remote HEAD sha of the work branch, or None."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", REMOTE, f"refs/heads/{BRANCH}"],
            capture_output=True, text=True, timeout=60).stdout.strip()
        return out.split()[0] if out else None
    except Exception:
        return None


def dom_state():
    """Live DOM of the worker chat tab (self-healing).

    2026-10-05 16:05Z incident: the worker VIEW tab's renderer crashed
    mid-turn (watcher CDP timeout) and the tab reset to the chat.z.ai home
    URL — find_tab's fall-through then matched a HOME tab and the watcher
    would have monitored the wrong DOM (bodyLen ~2K static) into a false
    STALLED2. Guard: the returned tab's URL must contain the chat id;
    otherwise open a fresh tab at the chat URL (the worker executes
    SERVER-SIDE — the tab is only a view, freely replaceable)."""
    try:
        tab = channel.find_tab(CHAT[:8])
        if not tab or CHAT[:8] not in (tab.get("url") or ""):
            log("view tab lost/reset — opening a fresh one")
            channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
            time.sleep(12)
            tab = channel.find_tab(CHAT[:8])
            if not tab or CHAT[:8] not in (tab.get("url") or ""):
                return None
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
        try:
            return json.loads(ws.eval(r"""(() => {
  const body = document.body.innerText || '';
  const stop = [...document.querySelectorAll('button')].some(
    b => (b.innerText || '').toLowerCase().includes('stop')
      && getComputedStyle(b).display !== 'none');
  const tail = body.slice(-12000);
  const report = /work\/P4-W4-003/i.test(tail) || /CERTIFICATION REPORT/i.test(tail);
  const shas = (body.slice(-12000).match(/[0-9a-f]{40}/g) || []);
  return JSON.stringify({
    bodyLen: body.length, generating: stop,
    report: report, tailSha: shas.length ? shas[shas.length-1] : null
  });
})()"""))
        finally:
            ws.close()
    except Exception as e:
        log(f"dom_state error: {type(e).__name__}: {e}")
        return None


def main():
    log(f"armed — live-DOM delivery watch, cycle {CYCLE}s, window {WINDOW//3600}h")
    t0 = time.time()
    last_body = -1
    last_head = None
    last_move = time.time()
    while time.time() - t0 < WINDOW:
        head = branch_head()
        st = dom_state()
        if st is None:
            log("no DOM — cycle skipped")
            time.sleep(CYCLE)
            continue
        moved = (head != last_head) or (st["bodyLen"] != last_body)
        if moved:
            last_move = time.time()
        last_head = head
        last_body = st["bodyLen"]
        if head and head != BASE_SHA and st["report"] and st["tailSha"] \
                and not st["generating"]:
            log(f"DELIVERED — branch {head[:10]}, report in DOM, sha {st['tailSha'][:10]}")
            open(os.path.join(FLAGS, "w4003_delivered"), "w").write(
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                + f" head={head}\n")
            return 0
        idle = int((time.time() - last_move) // 60)
        b = "branch@" + head[:10] if head else "branch-absent"
        if head and head != last_head:
            log(f"push observed — {b}")
        if st["report"]:
            log(f"report marker visible but incomplete (gen={st['generating']} "
                f"sha={st['tailSha']}) — {b}")
        elif idle * 60 >= STALL_AFTER:
            log(f"STALLED — {b}, idle {idle}m, gen={st['generating']}")
            fp = os.path.join(FLAGS, "w4003_stalled")
            if not os.path.exists(fp):
                open(fp, "w").write(
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    + f" head={head} idle={idle}m\n")
        else:
            log(f"working — {b}, bodyLen={st['bodyLen']}, gen={st['generating']}, idle {idle}m")
        time.sleep(CYCLE)
    log("WINDOW EXPIRED")
    open(os.path.join(FLAGS, "w4003_watch_timeout"), "w").write(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
