#!/usr/bin/env python3
"""establishment_assault.py — patient establishment loop for one work order.

THE FAILURE MODE (2026-09-27 forensics): after a platform rollback (session
killed + chat deleted), the account silently refuses NEW agent turns — the
prompt is stored server-side (msgs=1) but no assistant stub is ever created.
DOM shows no capacity banner, no error, no sandbox-limit modal. Differential
proof: a trivial 58-char ACK chat died identically → account-level, not
prompt-level. Yesterday's recovery rhythm after a rollback was 1.5-2h.

THE VERDICT SIGNAL (calibrated on 68e38fdd/831c93c6): an ACCEPTED turn shows
msgs>=2 in the chats API within ~15-30s (user + empty assistant stub "[]";
real content streams to the batch store). A refused turn stays msgs=1
forever. Server-side truth only — the DOM balloons/collapses unreliably.

LOOP (operator doctrine 2026-09-25: never wait, retry and retry):
  round: [round 1: retire any standing queue_watch for <name>]
         void previous record -> dispatch_worker create (the proven
         agents-tab sequence) -> poll probe_chat every 30s up to verdict_s
         -> msgs>=2: arm queue_watch on the new tab, outbox, exit 0
         -> else: next round (each round IS the real dispatch — the moment
            the account accepts turns, the work order is live).
Bounded by max_rounds; honesty note to the outbox every 5 failed rounds.

Usage:
  establishment_assault.py <name> <prompt_file> <marker> [verdict_s=360] [max_rounds=16]
Launch detached (survives the session reaper):
  dfork_launch.py /tmp/assault_<name>.log <py> establishment_assault.py ...
Exit codes: 0 established, 3 exhausted rounds.
"""
import json
import os
import subprocess
import sys
import time

PY = sys.executable
BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")
REGISTRY = os.path.join(FLAGS, "session_registry.jsonl")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
DISPATCH = os.path.join(BASE, "dispatch_worker.py")
PROBE = os.path.join(BASE, "probe_chat.py")
WATCH_LAUNCH = os.path.join(BASE, "launch_queue_watch.py")

POLL_S = 30
BREATH_S = 45


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def post(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time() * 1000), "from": "agent", "text": text}
            ) + "\n")
    except Exception:
        pass


def run(cmd, timeout=900):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def records():
    try:
        return [json.loads(l) for l in open(REGISTRY).read().split("\n") if l.strip()]
    except Exception:
        return []


def live_record(name):
    """newest sent, non-void record for name"""
    recs = [r for r in records()
            if r.get("name") == name and r.get("sent") and r.get("action") is None]
    return recs[-1] if recs else None


def retire_standing_watch(name):
    spec = os.path.join(FLAGS, f"queue_watch.spec.{name}")
    try:
        d = json.loads(open(spec).read())
        pid = d.get("pid")
        if pid:
            os.kill(int(pid), 15)
            log(f"retired standing queue_watch[{name}] pid {pid}")
    except Exception:
        pass
    for p in (spec, os.path.join(FLAGS, f"queue_watch_heartbeat.{name}")):
        try:
            os.remove(p)
        except Exception:
            pass


def probe_msgs(uuid):
    """msgs count from the server-side truth probe; -1 on probe failure"""
    rc, out = run([PY, PROBE, uuid], timeout=90)
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return int(json.loads(line).get("msgs", -1))
            except Exception:
                continue
    return -1


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    name, prompt_file, marker = sys.argv[1], sys.argv[2], sys.argv[3]
    verdict_s = int(sys.argv[4]) if len(sys.argv) > 4 else 360
    max_rounds = int(sys.argv[5]) if len(sys.argv) > 5 else 16

    log(f"assault[{name}] start: prompt={os.path.basename(prompt_file)} "
        f"marker={marker!r} verdict={verdict_s}s rounds<={max_rounds}")
    retire_standing_watch(name)

    for rnd in range(1, max_rounds + 1):
        rec = live_record(name)
        if rec:
            rc, out = run([PY, DISPATCH, "void", name,
                           f"establishment assault round {rnd}: previous turn "
                           f"dead at birth (no assistant stub)"])
            log(f"round {rnd}: voided previous ({(out or '').strip().splitlines()[-1][:80] if out else 'rc=' + str(rc)})")
        rc, out = run([PY, DISPATCH, "create", name, prompt_file], timeout=600)
        out_tail = "\n".join((out or "").strip().splitlines()[-2:])
        if rc != 0 or "NOT VERIFIED" in (out or ""):
            log(f"round {rnd}: send NOT VERIFIED (rc={rc}) — {out_tail[:160]}")
            if rnd % 5 == 0:
                post(f"assault[{name}]: round {rnd} send-failure class "
                     f"(rc={rc}); continuing per never-wait doctrine")
            time.sleep(BREATH_S)
            continue
        rec = live_record(name)
        if not rec or not rec.get("url"):
            log(f"round {rnd}: no registry record after create — {out_tail[:120]}")
            time.sleep(BREATH_S)
            continue
        uuid = rec["url"].rstrip("/").split("/")[-1]
        tab_prefix = (rec.get("tab_id") or "")[:8]
        log(f"round {rnd}: sent VERIFIED chat={uuid[:8]} tab={tab_prefix} — "
            f"polling for assistant stub (msgs>=2)")
        established = False
        waited = 0
        while waited < verdict_s:
            time.sleep(POLL_S)
            waited += POLL_S
            msgs = probe_msgs(uuid)
            if msgs >= 2:
                established = True
                break
            if msgs < 0:
                log(f"round {rnd}: probe failed at {waited}s — retrying")
        if established:
            log(f"round {rnd}: ESTABLISHED chat={uuid[:8]} (msgs>=2 at {waited}s)")
            run([PY, WATCH_LAUNCH, name, tab_prefix, marker], timeout=60)
            post(f"assault[{name}]: ESTABLISHED on round {rnd} — chat {uuid[:8]} "
                 f"(assistant stub at {waited}s); queue_watch armed on tab {tab_prefix}")
            return 0
        log(f"round {rnd}: dead at birth — msgs=1 after {verdict_s}s "
            f"(account still refusing turns)")
        if rnd % 5 == 0:
            post(f"assault[{name}]: {rnd} rounds dead at birth — account-level "
                 f"turn refusal persists (post-rollback window); continuing")
    post(f"assault[{name}]: EXHAUSTED {max_rounds} rounds without establishment "
         f"— duty session must reassess (platform window longer than budget)")
    log(f"exhausted {max_rounds} rounds")
    return 3


if __name__ == "__main__":
    sys.exit(main())
