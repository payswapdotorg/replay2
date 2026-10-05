#!/usr/bin/env python3
"""w4002_delivery_watch2.py — live-DOM truth watcher for the W4-002 re-run.

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

Usage: dfork_launch.py logs/w4002_delivery2.log python3 w4002_delivery_watch2.py
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

CHAT = "476b5e05-b67c-47f0-8c3f-a5e7cd3c429c"
BRANCH = "work/P4-W4-002"
BASE_SHA = "852941a"
REMOTE = "https://github.com/payswapdotorg/payswap.org.git"
FLAGS = os.path.join(BASE, "flags")
CYCLE = 300          # 5 min
STALL_AFTER = 90 * 60
WINDOW = 14 * 3600
SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")


def log(msg):
    print(f"[w4002-d2 {time.strftime('%H:%M:%S')}] {msg}", flush=True)


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
    """Live DOM of the worker chat tab (opens one if absent)."""
    try:
        tab = channel.find_tab(CHAT[:8])
        if not tab:
            channel.new_tab(f"https://chat.z.ai/c/{CHAT}")
            time.sleep(12)
            tab = channel.find_tab(CHAT[:8])
            if not tab:
                return None
        ws = channel.CDP(tab["webSocketDebuggerUrl"], timeout=60)
        try:
            return json.loads(ws.eval(r"""(() => {
  const body = document.body.innerText || '';
  const stop = [...document.querySelectorAll('button')].some(
    b => (b.innerText || '').toLowerCase().includes('stop')
      && getComputedStyle(b).display !== 'none');
  const tail = body.slice(-12000);
  const report = /FINAL DELIVERY REPORT/i.test(tail);
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
            open(os.path.join(FLAGS, "w4002_delivered"), "w").write(
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
            fp = os.path.join(FLAGS, "w4002_stalled2")
            if not os.path.exists(fp):
                open(fp, "w").write(
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    + f" head={head} idle={idle}m\n")
        else:
            log(f"working — {b}, bodyLen={st['bodyLen']}, gen={st['generating']}, idle {idle}m")
        time.sleep(CYCLE)
    log("WINDOW EXPIRED")
    open(os.path.join(FLAGS, "w4002_watch2_timeout"), "w").write(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
