#!/usr/bin/env python3
"""w100_watch.py — resident completion watch for the Wave 9 lanes (W100A/B/C).

Field laws applied (w090c + p2fix lessons):
  - OWN-tab probe per worker; the tab is the source of truth.
  - Liveness: growth in EITHER the thinking-chain DOM
    (.thinking-chain-container) OR the body content-hash (length alone lies —
    the chat UI caps rendered body length; the w090c lesson).
  - Completion = the UN-FORGEABLE signature: a 'W100X COMPLETION REPORT'
    block followed by 'Pushed: work/w100x <hex sha> <N> tests'. The echoed
    prompt template carries '<full 40-hex sha>' placeholders and can never
    match.
  - Push detect (secondary truth): git ls-remote origin refs/heads/work/w100x.
  - Stall (30 min zero growth): auto-nudge continuation (max 3 per lane),
    outbox note each time.
  - On lane completion: flags/w100<lane>_done.json + outbox. Exit when all
    three lanes are done (harvest is the TL's next move).
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
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
FLEETOS = "/home/z/fleetos"

LANES = [
    {"name": "w100a", "item": "W100A", "branch": "work/w100a",
     "url": "https://chat.z.ai/c/8a7cca37-703b-4d5d-ac60-9b619b22b524",
     "chat_id": "8a7cca37-703b-4d5d-ac60-9b619b22b524"},
    {"name": "w100b", "item": "W100B", "branch": "work/w100b",
     "url": "https://chat.z.ai/c/f7cb1d41-e717-4fa3-91c9-182bd669791b",
     "chat_id": "f7cb1d41-e717-4fa3-91c9-182bd669791b"},
    {"name": "w100c", "item": "W100C", "branch": "work/w100c",
     "url": "https://chat.z.ai/c/fe867357-2a9e-4313-af41-8f7d65d09d39",
     "chat_id": "fe867357-2a9e-4313-af41-8f7d65d09d39"},
]

CYCLE_S = 120
STALL_S = 30 * 60
MAX_NUDGES = 3

REAL_REPORT_RES = {
    lane["item"]: re.compile(
        r"%s COMPLETION REPORT[\s\S]{0,600}?"
        r"Pushed:\s*%s\s+[0-9a-f]{7,40}\s+\d+ tests" % (lane["item"], lane["branch"]))
    for lane in LANES
}

PROBE_JS = r"""(() => {
  const think = document.querySelector('.thinking-chain-container');
  const txt = document.body.innerText || '';
  return JSON.stringify({
    url: location.href,
    bodyLen: txt.length,
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


def own_tab(chat_id):
    for t in channel.list_tabs():
        if chat_id in (t.get("url") or ""):
            return t
    return None


def probe(lane):
    """(body_text, state) from the worker's OWN tab, or (None, None)."""
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
        "(bun run check / bun run typecheck / bun test), push work/%s to "
        "origin, then end your final message with the exact '%s COMPLETION "
        "REPORT' block from the work order with the REAL 40-hex sha and REAL "
        "test counts (never the template placeholders). If you are blocked, "
        "report the blocker honestly." % (lane["item"], lane["name"], lane["item"]))
    try:
        res = channel.send_text(msg)
        ok = bool(res.get("ok"))
        log("%s nudge send ok=%s detail=%s" % (lane["name"], ok, res.get("detail", "")))
        return ok
    except Exception as e:
        log("%s nudge error: %s" % (lane["name"], e))
        return False


def remote_sha(branch):
    try:
        out = subprocess.run(
            ["git", "ls-remote", "origin", "refs/heads/" + branch],
            cwd=FLEETOS, capture_output=True, text=True, timeout=30)
        line = (out.stdout or "").strip().split("\t")[0]
        return line if re.fullmatch(r"[0-9a-f]{40}", line) else None
    except Exception:
        return None


def main():
    done = {}
    state = {}
    for lane in LANES:
        flag = os.path.join(FLAGS, "%s_done.json" % lane["name"])
        if os.path.exists(flag):
            try:
                done[lane["name"]] = json.load(open(flag))
            except Exception:
                done[lane["name"]] = {"note": "pre-existing flag"}
        state[lane["name"]] = {
            "last_growth": time.time(), "body_hash": None, "think_len": 0,
            "nudges": 0, "pushed_sha": None,
        }
    log("Wave 9 watch armed: lanes=%s done_pre=%s cycle=%ss stall=%ss" %
        ([l["name"] for l in LANES], list(done), CYCLE_S, STALL_S))

    while len(done) < len(LANES):
        time.sleep(CYCLE_S)
        for lane in LANES:
            n = lane["name"]
            if n in done:
                continue
            txt, st = probe(lane)
            if txt is None:
                log("%s no tab / probe fail — retry next cycle" % n)
                continue
            body_hash = hashlib.sha256(txt.encode(errors="replace")).hexdigest()[:16]
            think_len = int((st or {}).get("thinkLen") or 0)
            s = state[n]
            grew = body_hash != s["body_hash"] or think_len != s["think_len"]
            if grew:
                s["last_growth"] = time.time()
                s["body_hash"] = body_hash
                s["think_len"] = think_len
                log("%s alive: hash=%s think=%d tail=%r" %
                    (n, body_hash, think_len, (st or {}).get("tail", "")[-80:]))
            # push truth (cheap, once per cycle)
            sha = remote_sha(lane["branch"])
            if sha and sha != s["pushed_sha"]:
                s["pushed_sha"] = sha
                log("%s PUSHED: %s @ %s" % (n, lane["branch"], sha))
                outbox("%s pushed %s @ %s (report pending)" % (lane["item"], lane["branch"], sha))
            # completion oracle
            m = REAL_REPORT_RES[lane["item"]].search(txt)
            if m:
                rec = {
                    "item": lane["item"], "branch": lane["branch"],
                    "report_excerpt": m.group(0)[:300], "pushed_sha": s["pushed_sha"],
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                open(os.path.join(FLAGS, "%s_done.json" % n), "w").write(json.dumps(rec, indent=2))
                done[n] = rec
                log("%s COMPLETION REPORT VERIFIED: %r" % (n, m.group(0)[:120]))
                outbox("%s COMPLETION REPORT verified on own tab: %s" % (lane["item"], m.group(0)[:200]))
                continue
            # stall + nudge
            idle = time.time() - s["last_growth"]
            if idle > STALL_S and s["nudges"] < MAX_NUDGES:
                s["nudges"] += 1
                log("%s STALLED %.0f min — nudge %d/%d" % (n, idle / 60, s["nudges"], MAX_NUDGES))
                outbox("%s stalled %.0f min — TL nudge %d" % (lane["item"], idle / 60, s["nudges"]))
                if send_nudge(lane):
                    s["last_growth"] = time.time()
            elif idle > STALL_S:
                log("%s stalled %.0f min, nudge budget exhausted (%d)" % (n, idle / 60, s["nudges"]))

    open(os.path.join(FLAGS, "w100_all_done.json"), "w").write(json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lanes": {n: (done.get(n) or {}).get("pushed_sha") for n in done},
    }, indent=2))
    log("ALL THREE LANES DONE — exiting for TL harvest")
    outbox("WAVE 9: all three lanes report completion — TL harvest next")
    return 0


if __name__ == "__main__":
    sys.exit(main())
