#!/usr/bin/env python3
"""resumption_watch.py — platform-degradation resumption detector (2026-09-22).

Context: both staged agent sends (hfx204 04:29, hfx101 06:30) landed but
their generation tasks were silently dropped (chars flat at the 786-char
empty-message JSON skeleton for hours); the plain canary also fails
proof on send. The no-churn doctrine forbids re-dispatch during the
degradation. This watcher detects RESUMPTION:

  every cycle (default 240s):
    1. probe each named dead chat via batch_probe — chars GROWTH > +200
       means its queued task came alive (ADOPT-worthy)
    2. every 4th cycle, fire plain_liveness_probe.py — a materialized
       replied canary means the platform send path is healthy again

On either signal: write flags/platform-resumed.marker + post the outbox,
then exit 0. On max-hours burnout: exit 3.

Usage: resumption_watch.py <name>:<chat-id> [<name>:<chat-id> ...]
       [--every 240] [--max-hours 12]
"""
import json, os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
FLAGS = os.path.join(BASE, "flags")

def log(line):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {line}", flush=True)

def post_outbox(text):
    rec = {"ts": int(time.time()*1000), "text": text}
    with open(os.path.join(FLAGS, "agent_outbox.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")

def probe_chars(cid):
    try:
        out = subprocess.run([sys.executable, os.path.join(BASE, "batch_probe.py"), cid, "x"],
                             capture_output=True, text=True, timeout=45)
        d = json.loads(out.stdout.strip().splitlines()[-1])
        asst = [m for m in d.get("messages", []) if m.get("role") == "assistant"]
        return int(asst[-1].get("chars") or 0) if asst else 0
    except Exception:
        return None

def canary():
    try:
        out = subprocess.run([sys.executable, os.path.join(BASE, "plain_liveness_probe.py")],
                             capture_output=True, text=True, timeout=280)
        last = [l for l in (out.stdout or "").strip().splitlines() if l.startswith("{")]
        if not last: return None
        d = json.loads(last[-1])
        return bool(d.get("replied"))
    except Exception:
        return None

def main():
    args = sys.argv[1:]
    every, max_h = 240, 12
    if "--every" in args:
        i = args.index("--every"); every = int(args[i+1]); del args[i:i+2]
    if "--max-hours" in args:
        i = args.index("--max-hours"); max_h = float(args[i+1]); del args[i:i+2]
    jobs = []
    for a in args:
        n, cid = a.split(":", 1)
        jobs.append((n, cid))
    baseline = {n: probe_chars(cid) for n, cid in jobs}
    log(f"watching {[(n, c[:8], baseline[n]) for n, c in jobs]} every={every}s")
    deadline = time.time() + max_h*3600
    cycle = 0
    while time.time() < deadline:
        time.sleep(every)
        cycle += 1
        for n, cid in jobs:
            c = probe_chars(cid)
            b = baseline.get(n)
            if c is not None and b is not None and c > b + 200:
                msg = f"PLATFORM RESUMPTION: {n} ({cid[:8]}) work log GROWING ({b} -> {c} chars) — the queued task came alive; ADOPT the session"
                log(msg)
                open(os.path.join(FLAGS, "platform-resumed.marker"), "w").write(f"{n} {cid} {int(time.time())}\n")
                post_outbox(msg)
                return 0
        if cycle % 4 == 0:
            r = canary()
            log(f"canary cycle {cycle}: replied={r}")
            if r:
                msg = f"PLATFORM RESUMPTION: plain canary replied (send path healthy) — re-dispatch window OPEN for hfx204/hfx101"
                log(msg)
                open(os.path.join(FLAGS, "platform-resumed.marker"), "w").write(f"canary {int(time.time())}\n")
                post_outbox(msg)
                return 0
    log("burnout: no resumption signal within max-hours")
    return 3

if __name__ == "__main__":
    raise SystemExit(main())
