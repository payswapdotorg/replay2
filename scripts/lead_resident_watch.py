#!/usr/bin/env python3
"""lead_resident_watch.py — CONTINUOUS resident watch (operator directive
2026-10-01: monitor -> harvest -> review -> approve/require-changes ->
dispatch next, until the roadmap is complete. No early returns).

Resident laws:
  - NEVER exits. Each cycle re-reads flags/session_registry.jsonl, so lanes
    dispatched AFTER startup are picked up automatically (the TL dispatches
    the next lane on each harvest; this watcher just keeps watching).
  - Per ACTIVE (not done, not void) session: liveness = body content-hash
    OR thinking-chain growth (length alone lies).
  - Completion = the un-forgeable oracle: '<ITEM> COMPLETION REPORT'
    followed by 'Pushed: <branch> <hex sha> <N> tests' on the worker's OWN
    tab. Push truth cross-checked via git ls-remote.
  - Stall (30 min zero growth): auto-nudge continuation, max 3 per lane.
  - On completion: flags/<name>_done.json + outbox note. The TL (in-session)
    harvests, reviews, approves (merge) or sends require-changes; the next
    dispatch lands in the registry and the loop continues.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
FLEETOS = "/home/z/fleetos"

CYCLE_S = 120
STALL_S = 30 * 60
MAX_NUDGES = 3

PROBE_JS = r"""(() => {
  const think = document.querySelector('.thinking-chain-container');
  const txt = document.body.innerText || '';
  return JSON.stringify({
    url: location.href, bodyLen: txt.length,
    thinkLen: think ? think.textContent.length : 0,
    tail: txt.slice(-160)
  });
})()"""


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def outbox(text):
    os.makedirs(FLAGS, exist_ok=True)
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": int(time.time() * 1000), "from": "agent", "text": text}) + "\n")


def active_lanes():
    """Registry entries not done/void; done flags short-circuit."""
    lanes = []
    try:
        for line in open(REG, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("sent") is not True:
                continue
            name = r.get("name", "")
            if not name:
                continue
            if os.path.exists(os.path.join(FLAGS, "%s_done.json" % name)):
                continue  # already flagged done; watcher stays quiet
            if r.get("done") or r.get("void"):
                continue
            url = r.get("url", "")
            m = re.search(r"/c/([0-9a-f-]{36})", url)
            if not m:
                continue
            lanes.append({"name": name, "chat_id": m.group(1), "url": url})
    except FileNotFoundError:
        pass
    return lanes


def own_tab(chat_id):
    for t in channel.list_tabs():
        if chat_id in (t.get("url") or ""):
            return t
    return None


def probe(lane):
    tab = own_tab(lane["chat_id"])
    if not tab:
        return None, None
    try:
        c = channel.CDP(tab["webSocketDebuggerUrl"], timeout=30)
        try:
            txt = c.eval("(document.body.innerText || '')", timeout=30) or ""
            st = None
            try:
                v = c.eval(PROBE_JS, timeout=30)
                st = json.loads(v) if v else None
            except Exception:
                pass
            return txt, st
        finally:
            c.close()
    except Exception as e:
        log("%s probe failed: %s" % (lane["name"], e))
        return None, None


def send_nudge(lane):
    msg = (
        "[TL rescue] Continue the %s work order autonomously from exactly "
        "where you left off. Do not re-introduce yourself and do not restart "
        "finished work. Finish the remaining scope, run the gate set "
        "(bun run check / bun run typecheck / bun test), push your work "
        "branch to origin, then end your final message with the exact "
        "COMPLETION REPORT block from the work order with the REAL 40-hex "
        "sha and REAL test counts. If you are blocked, report the blocker "
        "honestly." % lane["name"])
    try:
        res = channel.send_text(msg)
        log("%s nudge ok=%s detail=%s" % (lane["name"], res.get("ok"), res.get("detail", "")))
        return bool(res.get("ok"))
    except Exception as e:
        log("%s nudge error: %s" % (lane["name"], e))
        return False


def remote_sha(branch):
    try:
        out = subprocess.run(["git", "ls-remote", "origin", "refs/heads/" + branch],
                             cwd=FLEETOS, capture_output=True, text=True, timeout=30)
        line = (out.stdout or "").strip().split("\t")[0]
        return line if re.fullmatch(r"[0-9a-f]{40}", line) else None
    except Exception:
        return None


def branch_of(name):
    """w120 -> work/w120; falls back to the name itself."""
    return "work/" + re.sub(r"^work/", "", name)


STATE = {}  # name -> {last_growth, body_hash, think_len, nudges, pushed_sha}


def main():
    log("LEAD RESIDENT WATCH armed (continuous; cycle=%ss stall=%ss nudges=%d)" % (CYCLE_S, STALL_S, MAX_NUDGES))
    while True:
        for lane in active_lanes():
            n = lane["name"]
            if n not in STATE:
                STATE[n] = {"last_growth": time.time(), "body_hash": None,
                            "think_len": 0, "nudges": 0, "pushed_sha": None}
                log("lane picked up: %s (%s)" % (n, lane["chat_id"]))
            s = STATE[n]
            txt, st = probe(lane)
            if txt is None:
                continue
            body_hash = hashlib.sha256(txt.encode(errors="replace")).hexdigest()[:16]
            think_len = int((st or {}).get("thinkLen") or 0)
            grew = body_hash != s["body_hash"] or think_len != s["think_len"]
            if grew:
                s["last_growth"] = time.time()
                s["body_hash"] = body_hash
                s["think_len"] = think_len
                log("%s alive: hash=%s think=%d tail=%r" % (n, body_hash, think_len, (st or {}).get("tail", "")[-70:]))
            # push truth
            sha = remote_sha(branch_of(n))
            if sha and sha != s["pushed_sha"]:
                s["pushed_sha"] = sha
                log("%s PUSHED: %s @ %s" % (n, branch_of(n), sha))
                outbox("%s pushed %s @ %s (report pending)" % (n, branch_of(n), sha))
            # un-forgeable completion oracle (generic W-item format)
            m = re.search(r"(W1[0-9]{2}) COMPLETION REPORT[\s\S]{0,600}?Pushed:\s*(\S+)\s+([0-9a-f]{7,40})\s+(\d+) tests", txt)
            if m and m.group(2) == branch_of(n):
                rec = {"item": m.group(1), "branch": m.group(2), "sha": m.group(3),
                       "tests": m.group(4), "pushed_sha": s["pushed_sha"],
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "report_excerpt": m.group(0)[:300]}
                open(os.path.join(FLAGS, "%s_done.json" % n), "w").write(json.dumps(rec, indent=2))
                log("%s COMPLETION REPORT VERIFIED: %s @ %s %s tests" % (n, m.group(2), m.group(3), m.group(4)))
                outbox("%s COMPLETION REPORT verified: %s @ %s %s tests — TL harvest next" % (n, m.group(2), m.group(3), m.group(4)))
                continue
            # stall + nudge
            idle = time.time() - s["last_growth"]
            if idle > STALL_S and s["nudges"] < MAX_NUDGES:
                s["nudges"] += 1
                log("%s STALLED %.0fmin — nudge %d/%d" % (n, idle / 60, s["nudges"], MAX_NUDGES))
                if send_nudge(lane):
                    outbox("%s stalled; TL nudge %d sent" % (n, s["nudges"]))
            elif idle > STALL_S and s["nudges"] >= MAX_NUDGES:
                log("%s STALLED with nudge budget exhausted — TL intervention needed" % n)
                outbox("%s stalled; nudge budget exhausted — TL must intervene" % n)
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    main()
