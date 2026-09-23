#!/usr/bin/env python3
"""endgame_recover.py — auto-recovery chain for the global-limit wedge.

2026-09-23 context: both endgame lanes (prod033 b90ee795, hfx302 8671b28b)
were dispatched 11:23-11:25 UTC into a "Global limit reached, please try
again later" regime — sends accepted server-side but generation refused;
hfx302's tab was later rolled home by the site (chat survives server-side,
un-answered). backend_probe.py confirms the wedge stands (junk-chat OK
probes land but never generate — never touches worker sessions).

Chain (this sentinel, detached):
  1. wait for flags/backend_recovered.txt (mtime > sentinel start) —
     written by backend_probe_watch.py on its first HEALTHY verdict;
  2. settle 120s (avoid a one-off blip window);
  3. kill stale completion watches bound to the OLD chat-id needles;
  4. void the errored lane sessions in the registry (bookkeeping);
  5. fresh re-dispatch both lanes (launch_create.py, staggered 30s);
  6. poll the registry for fresh sent records -> new chat ids;
  7. rewrite dispatched markers + flags/endgame_lanes.json;
  8. outbox narration; exit 0 — the supervisor endgame guard arms the
     new completion watches + lane_watch on its next 10s cycle.

Retry policy: up to 6 dispatch rounds (10 min backoff between). Names
with a fresh sent record are not re-dispatched (create is destructive to
a live session). Exit 1 + outbox alert if all rounds fail.

Usage: endgame_recover.py   (launch via launch_detached.py)
"""
import json
import os
import subprocess
import time

BASE = "/home/z/replay2/scripts"
ROOT = "/home/z/replay2"
FLAGS = os.path.join(BASE, "flags")
REG = os.path.join(FLAGS, "session_registry.jsonl")
RECOVERED = os.path.join(FLAGS, "backend_recovered.txt")
LANES = os.path.join(FLAGS, "endgame_lanes.json")
OUTBOX = os.path.join(FLAGS, "agent_outbox.jsonl")
PY = "/home/z/.venv/bin/python3"

PROMPTS = {
    "prod033": os.path.join(BASE, "worker-prompts", "PROD033.md"),
    "hfx302": os.path.join(BASE, "worker-prompts", "HFX302.md"),
}
OLD_CIDS = {"prod033": "b90ee795", "hfx302": "8671b28b"}


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def outbox(text):
    try:
        with open(OUTBOX, "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time() * 1000), "from": "agent", "text": text})
                + "\n")
    except OSError as e:
        log(f"outbox write failed: {e}")


def reg_latest(name):
    """Last registry record for name (dict or None)."""
    rec = None
    try:
        with open(REG) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("name") == name:
                    rec = d
    except FileNotFoundError:
        return None
    return rec


def reg_append(record):
    with open(REG, "a") as f:
        f.write(json.dumps(record) + "\n")


def kill_old_watches():
    """Kill waveB_completion_watch processes bound to OLD chat needles."""
    out = subprocess.run(["pgrep", "-f", "waveB_completion_watch.py"],
                         capture_output=True, text=True).stdout.split()
    killed = []
    for pid in out:
        try:
            cmd = open(f"/proc/{int(pid)}/cmdline", "rb").read().decode(
                errors="replace")
        except OSError:
            continue
        for name, cid in OLD_CIDS.items():
            if f"{name}:{cid}" in cmd:
                subprocess.run(["kill", pid], capture_output=True)
                killed.append(f"{name}:{cid} (pid {pid})")
    if killed:
        log("killed stale watches: " + ", ".join(killed))


def dispatch_round(t0):
    """One dispatch round for lanes lacking a fresh sent record.
    Returns {name: chat-id-prefix} for lanes newly (or already) landed."""
    landed = {}
    for name, prompt in PROMPTS.items():
        rec = reg_latest(name)
        if rec and rec.get("sent") and int(rec.get("ts", 0)) > t0:
            cid = (rec.get("url") or "").split("/c/")[-1][:8]
            if len(cid) == 8:
                landed[name] = cid
                log(f"{name}: already landed this round (chat {cid})")
            continue
        log(f"{name}: launching fresh create ({prompt})")
        subprocess.run(
            [PY, os.path.join(BASE, "launch_create.py"), name, prompt],
            capture_output=True, text=True, cwd=ROOT, timeout=60)
        time.sleep(30)  # stagger: create navigates tabs sequentially
    # poll registry up to 15 min for sent records
    deadline = time.time() + 900
    while time.time() < deadline and len(landed) < len(PROMPTS):
        for name in PROMPTS:
            if name in landed:
                continue
            rec = reg_latest(name)
            if rec and rec.get("sent") and int(rec.get("ts", 0)) > t0:
                cid = (rec.get("url") or "").split("/c/")[-1][:8]
                if len(cid) == 8:
                    landed[name] = cid
                    log(f"{name}: ACCEPTED chat {cid}")
        if len(landed) < len(PROMPTS):
            time.sleep(30)
    return landed


def rewire(landed):
    """Markers + endgame_lanes.json + old-session void bookkeeping."""
    now = time.strftime("%H:%M:%S")
    lanes = {}
    for name, cid in landed.items():
        open(os.path.join(FLAGS, f"{name}-dispatched.marker"), "w").write(
            f"{name} dispatched chat={cid} recovered at {now}\n")
        # void bookkeeping for the errored predecessor (same name, old ts)
        rec = reg_latest(name)
        if rec and rec.get("url") and OLD_CIDS.get(name) in rec.get("url", ""):
            pass  # latest is still the old record — nothing to void
        lanes[name] = cid
    with open(LANES, "w") as f:
        json.dump(lanes, f, indent=1)
    log(f"endgame_lanes.json rewritten: {lanes}")


def main():
    t0 = time.time()
    log("endgame_recover armed — waiting for backend_recovered marker "
        "(probe watch verdicts every 30 min)")
    # 1. wait for HEALTHY marker (fresh mtime)
    while True:
        try:
            if os.path.getmtime(RECOVERED) > t0:
                break
        except OSError:
            pass
        time.sleep(60)
    log("HEALTHY marker observed — settling 120s")
    time.sleep(120)
    # 2. clean stale watches + void errored sessions
    kill_old_watches()
    for name, cid in OLD_CIDS.items():
        rec = reg_latest(name)
        if rec and rec.get("sent") and cid in (rec.get("url") or ""):
            reg_append({"name": name, "action": "void",
                        "reason": f"global-limit wedge: chat {cid} errored "
                                  f"('Global limit reached') — abandoned for "
                                  f"fresh re-dispatch",
                        "ts": int(time.time())})
            log(f"{name}: old session {cid} voided (errored, un-answered)")
    # 3. dispatch rounds
    for rnd in range(1, 7):
        landed = dispatch_round(t0)
        if len(landed) == len(PROMPTS):
            rewire(landed)
            outbox("[lead] Generation capacity RECOVERED (probe HEALTHY). Both "
                   "endgame lanes freshly re-dispatched and ACCEPTED: "
                   + ", ".join(f"{n} → /c/{c}" for n, c in sorted(landed.items()))
                   + ". Completion watches re-armed; next stop: completion "
                     "reports → harvest → gates → merge → final redeploy.")
            log("RECOVERY COMPLETE — exiting 0")
            return 0
        log(f"round {rnd}: only {sorted(landed)} landed — backing off 10 min")
        outbox(f"[lead] recovery round {rnd}: partial landing "
               f"({sorted(landed) or 'none'}) — retrying in 10 min")
        time.sleep(600)
    outbox("[lead] ALERT: endgame_recover exhausted 6 dispatch rounds — "
           "lanes still not landed. Manual Lead attention required.")
    log("FAILED after 6 rounds — exiting 1")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
